#!/usr/bin/env python3
"""
dumbbot v6 — a conversational from-scratch LLM
Pure numpy. No APIs. Learns from YOU.

New in v6:
  - Proper subword tokenizer (handles contractions like didn't → did + n't)
  - Lower negative RL rate to prevent iBot-style corruption
  - Bigger architecture (EMBED_DIM=64, HIDDEN=512, CTX=8)
  - Corpus split into dumbbot_corpus.py for easier editing
  - Math mechanism for arithmetic questions
  - Punctuation added to generated responses
  - Gym progress saved inside model pkl
"""

import os, sys, math, random, pickle, re, time
import numpy as np

# ── Hyper-params ──────────────────────────────────────────────────────────────
CTX       = 8
EMBED_DIM = 64
HIDDEN    = 512
EPOCHS    = 600
LR_START  = 0.06
LR_END    = 0.004
MOMENTUM  = 0.88
BATCH     = 128
RL_LR_GOOD = 0.0015  # learning rate for good feedback
RL_LR_BAD  = 0.0002  # very small — prevents iBot-style corruption
RL_STEPS  = 8        # steps per positive feedback
MODEL_F   = os.path.expanduser("dumbbot6_model.pkl")

# ── Dialogue corpus — actual back-and-forth exchanges ────────────────────────
# Format: (user_says, bot_says)  — both sides get trained together
from dumbbot_corpus import DIALOGUES, SENTENCES



# ── Tokenizer ──────────────────────────────────────────────────────────────────────────────
def tokenize(text):
    """
    Proper subword tokenizer. Handles:
      - Contractions as whole tokens: didn't, won't, it's, I'm, they've
      - Punctuation: hello! -> ['hello', '!']
      - Numbers: 3.14 -> ['3.14']
      - Special tokens: <n> preserved as-is
      - Plain words: everything else lowercased
    """
    text = text.lower().replace('\u2019', "'").replace('\u2018', "'")
    return re.findall(
        r"[a-z]+n't|[a-z]+'s|[a-z]+'m|[a-z]+'re|[a-z]+'ve|[a-z]+'ll|[a-z]+'d"
        r"|<[^>]+>|[a-z]+|[0-9]+(?:\.[0-9]+)?|[.,!?;]",
        text
    )

# ── Vocabulary ────────────────────────────────────────────────────────────────────────────
def build_vocab(dialogues, sentences):
    counts = {}
    for u, b in dialogues:
        for w in tokenize(u + " " + b):
            counts[w] = counts.get(w, 0) + 1
    for s in sentences:
        for w in tokenize(s):
            counts[w] = counts.get(w, 0) + 1
    words = ["<S>", "</S>", "<n>"] + sorted(counts, key=lambda w: -counts[w])
    w2i = {w: i for i, w in enumerate(words)}
    i2w = {i: w for w, i in w2i.items()}
    return words, w2i, i2w

VOCAB, word2idx, idx2word = build_vocab(DIALOGUES, SENTENCES)
V = len(VOCAB)

def tok(w):
    """Look up a single token, fallback to 'i' if unknown."""
    return word2idx.get(w, word2idx.get("i", 0))

def detok(i):
    return idx2word.get(i, "")

def make_dataset(dialogues, sentences, ctx=CTX):
    X, Y = [], []
    s0 = word2idx["<S>"]
    e0 = word2idx["</S>"]

    # dialogue pairs: feed user side as context seed for bot side
    for user_str, bot_str in dialogues:
        u_ids = [tok(w) for w in tokenize(user_str)]
        b_ids = [tok(w) for w in tokenize(bot_str)] + [e0]
        buf = [s0] * ctx + u_ids
        for nxt in b_ids:
            X.append(buf[-ctx:])
            Y.append(nxt)
            buf.append(nxt)

    # plain sentences for fluency
    for sent in sentences:
        buf = [s0] * ctx
        ids = [tok(w) for w in tokenize(sent)] + [e0]
        for nxt in ids:
            X.append(buf[-ctx:])
            Y.append(nxt)
            buf.append(nxt)

    return np.array(X, np.int32), np.array(Y, np.int32)

# ── Model ─────────────────────────────────────────────────────────────────────
class DumbBot:
    def __init__(self):
        rng = np.random.default_rng(42)
        self.E  = rng.normal(0, 0.1, (V, EMBED_DIM))
        self.W1 = rng.normal(0, 0.1, (CTX * EMBED_DIM, HIDDEN))
        self.b1 = np.zeros(HIDDEN)
        self.W2 = rng.normal(0, 0.1, (HIDDEN, V))
        self.b2 = np.zeros(V)
        self.mE  = np.zeros_like(self.E)
        self.mW1 = np.zeros_like(self.W1)
        self.mb1 = np.zeros_like(self.b1)
        self.mW2 = np.zeros_like(self.W2)
        self.mb2 = np.zeros_like(self.b2)
        self.feedback_count = 0
        self.good_count     = 0
        self.bad_count      = 0
        self.known_name     = None   # remembers user's name this session
        # anchor weights — set after pre-training, used to prevent RL drift
        self.anchor_E  = None
        self.anchor_W1 = None
        self.anchor_W2 = None
        # gym progress — stored here so everything saves in one .pkl
        self.gym_level        = 0
        self.gym_total_good   = 0
        self.gym_total_bad    = 0
        self.gym_levels_passed = []

    def forward(self, x_ids):
        emb    = self.E[x_ids].reshape(len(x_ids), -1)
        h      = np.tanh(emb @ self.W1 + self.b1)
        logits = h @ self.W2 + self.b2
        return logits, emb, h

    def sup_step(self, x_ids, y_ids, lr):
        B = len(y_ids)
        logits, emb, h = self.forward(x_ids)
        lg    = logits - logits.max(1, keepdims=True)
        probs = np.exp(lg); probs /= probs.sum(1, keepdims=True)
        loss  = -np.mean(np.log(probs[np.arange(B), y_ids] + 1e-9))

        dl   = probs.copy(); dl[np.arange(B), y_ids] -= 1; dl /= B
        dW2  = h.T @ dl;        db2 = dl.sum(0)
        dh   = dl @ self.W2.T;  dh *= (1 - h**2)
        dW1  = emb.T @ dh;      db1 = dh.sum(0)
        demb = (dh @ self.W1.T).reshape(B, CTX, EMBED_DIM)
        dE   = np.zeros_like(self.E)
        np.add.at(dE, x_ids, demb)

        def upd(p, g, m):
            m[:] = MOMENTUM * m + (1 - MOMENTUM) * g
            p -= lr * m

        upd(self.E,  dE,  self.mE)
        upd(self.W1, dW1, self.mW1)
        upd(self.b1, db1, self.mb1)
        upd(self.W2, dW2, self.mW2)
        upd(self.b2, db2, self.mb2)
        return loss

    def rl_step(self, x_seq, y_seq, reward):
        steps = RL_STEPS if reward > 0 else 3   # bad feedback is a tiny nudge, not a shove
        for _ in range(steps):
            for x_ctx, y_tok in zip(x_seq, y_seq):
                xb = x_ctx[np.newaxis, :]
                logits, emb, h = self.forward(xb)
                lg    = logits - logits.max(1, keepdims=True)
                probs = np.exp(lg); probs /= probs.sum(1, keepdims=True)
                ec    = 0.02
                dl    = np.zeros_like(probs)
                dl[0, y_tok] = -reward
                dl   += ec * (probs + np.log(probs + 1e-9))

                dW2  = h.T @ dl;       db2 = dl.sum(0)
                dh   = dl @ self.W2.T; dh *= (1 - h**2)
                dW1  = emb.T @ dh;     db1 = dh.sum(0)
                demb = (dh @ self.W1.T).reshape(1, CTX, EMBED_DIM)
                dE   = np.zeros_like(self.E)
                np.add.at(dE, xb, demb)

                lr_now = RL_LR_GOOD if reward > 0 else RL_LR_BAD
                self.E  -= lr_now * dE
                self.W1 -= lr_now * dW1
                self.b1 -= lr_now * db1
                self.W2 -= lr_now * dW2
                self.b2 -= lr_now * db2
                # gravity: gently pull weights back toward pre-trained anchors
                # prevents runaway drift from too many bad ratings in a row
                GRAVITY = 0.008
                if self.anchor_E is not None:
                    self.E  -= GRAVITY * (self.E  - self.anchor_E)
                    self.W1 -= GRAVITY * (self.W1 - self.anchor_W1)
                    self.W2 -= GRAVITY * (self.W2 - self.anchor_W2)

    def generate(self, seed_ids, max_len=16, temp=0.85, top_k=22):
        # seed_ids is a full context array already
        ctx = list(seed_ids[-CTX:])
        out_ids  = []
        out_ctxs = []
        recent   = set(ctx[-4:])

        for _ in range(max_len):
            ctx_arr = np.array(ctx[-CTX:])
            logits, _, _ = self.forward(ctx_arr[np.newaxis, :])
            logits = logits[0] / max(temp, 0.1)
            logits -= logits.max()
            probs   = np.exp(logits); probs /= probs.sum()
            probs[0] = 0  # no <S>
            probs[1] *= 0.3  # lower </S> chance early on
            for r in recent:
                probs[r] *= 0.08
            probs /= probs.sum()

            top = np.argsort(probs)[-top_k:]
            p2  = probs[top]; p2 /= p2.sum()
            nxt = np.random.choice(top, p=p2)

            if detok(nxt) == "</S>" and len(out_ids) >= 3:
                break
            if detok(nxt) == "</S>":
                continue

            out_ctxs.append(ctx_arr)
            out_ids.append(nxt)
            ctx.append(nxt)
            recent = set(ctx[-4:])

        words = [detok(i) for i in out_ids]
        return " ".join(words) or "i am not sure what to say", out_ctxs, out_ids

    def save(self, path):
        with open(path, "wb") as f:
            d = {k: v for k, v in self.__dict__.items() if k != "known_name"}
            pickle.dump(d, f)

    def load(self, path):
        with open(path, "rb") as f:
            self.__dict__.update(pickle.load(f))
        # backwards compat: old saves won't have anchors
        if self.anchor_E is None and self.E is not None:
            self.anchor_E  = self.E.copy()
            self.anchor_W1 = self.W1.copy()
            self.anchor_W2 = self.W2.copy()

# ── Pre-training ──────────────────────────────────────────────────────────────
def pretrain(model):
    X, Y = make_dataset(DIALOGUES, SENTENCES)
    n    = len(X)
    print(f"  {n} samples  ·  vocab {V} words  ·  {EPOCHS} epochs")
    best = float("inf")
    t0   = time.time()
    for ep in range(1, EPOCHS + 1):
        lr   = LR_END + 0.5*(LR_START-LR_END)*(1+math.cos(math.pi*ep/EPOCHS))
        perm = np.random.permutation(n)
        Xs, Ys = X[perm], Y[perm]
        tot, steps = 0.0, 0
        for s in range(0, n, BATCH):
            tot   += model.sup_step(Xs[s:s+BATCH], Ys[s:s+BATCH], lr)
            steps += 1
        avg = tot / steps
        if avg < best: best = avg
        if ep % 25 == 0 or ep == EPOCHS:
            done    = int(30*ep/EPOCHS)
            elapsed = time.time()-t0
            eta     = int((elapsed/ep)*(EPOCHS-ep)) if ep > 0 else 0
            bar     = f"[{'█'*done}{'░'*(30-done)}]"
            print(f"\r  {bar} {ep}/{EPOCHS}  loss={avg:.4f}  eta {eta}s   ",
                  end="", flush=True)
    print(f"\n  Pre-training done ✓  best loss: {best:.4f}\n")
    # save anchors so RL can't drift too far from pre-trained quality
    model.anchor_E  = model.E.copy()
    model.anchor_W1 = model.W1.copy()
    model.anchor_W2 = model.W2.copy()


# ── Math mechanism ────────────────────────────────────────────────────────────
def try_math(text):
    """
    Detect and solve simple arithmetic questions.
    Returns a string answer if math detected, else None.
    """
    low = text.lower().strip().rstrip("?.")
    # word-number map
    wn = {
        "zero":0,"one":1,"two":2,"three":3,"four":4,"five":5,
        "six":6,"seven":7,"eight":8,"nine":9,"ten":10,
        "eleven":11,"twelve":12,"thirteen":13,"fourteen":14,"fifteen":15,
        "sixteen":16,"seventeen":17,"eighteen":18,"nineteen":19,"twenty":20,
        "thirty":30,"forty":40,"fifty":50,"sixty":60,"seventy":70,
        "eighty":80,"ninety":90,"hundred":100,
    }
    ops = {
        "plus":"+","add":"+","added":"+","and":"+",
        "minus":"-","subtract":"-","subtracted":"-","take away":"-",
        "times":"*","multiplied":"*","multiply":"*","x":"*",
        "divided":"/","divide":"/","over":"/",
        "squared":"**2","cubed":"**3",
    }

    def parse_num(s):
        s = s.strip()
        # try direct digit
        try: return float(s)
        except: pass
        # try word
        s2 = s.replace("-"," ")
        total, cur = 0, 0
        for w in s2.split():
            if w in wn:
                cur += wn[w]
            elif w == "hundred":
                cur *= 100
            elif w == "thousand":
                total += cur * 1000; cur = 0
        total += cur
        return float(total) if (total or s2.strip() in wn or s2.strip() == "zero") else None

    # pattern: "what is X <op> Y"
    import re as _re
    m = _re.search(
        r"what(?:\s+is)?\s+(.+?)\s+(plus|minus|times|multiplied by|divided by|add|subtract|take away)\s+(.+)",
        low)
    if m:
        a_str, op_str, b_str = m.group(1), m.group(2), m.group(3)
        a = parse_num(a_str)
        b = parse_num(b_str)
        if a is not None and b is not None:
            try:
                if   "plus"  in op_str or "add" in op_str:          result = a + b
                elif "minus" in op_str or "subtract" in op_str                      or "take away" in op_str:                       result = a - b
                elif "times" in op_str or "multiplied" in op_str:   result = a * b
                elif "divided" in op_str:
                    if b == 0: return "You cannot divide by zero."
                    result = a / b
                else: return None
                # format nicely
                ri = int(result)
                ans = str(ri) if result == ri else f"{result:.4f}".rstrip("0").rstrip(".")
                num_words = {0:"zero",1:"one",2:"two",3:"three",4:"four",5:"five",
                             6:"six",7:"seven",8:"eight",9:"nine",10:"ten",
                             11:"eleven",12:"twelve"}
                a_w = num_words.get(int(a), str(int(a))) if a == int(a) else str(a)
                b_w = num_words.get(int(b), str(int(b))) if b == int(b) else str(b)
                op_w = {"plus":"plus","add":"plus","minus":"minus",
                        "subtract":"minus","take away":"minus",
                        "times":"times","multiplied by":"times",
                        "divided by":"divided by"}.get(op_str, op_str)
                return f"{a_w.capitalize()} {op_w} {b_w} equals {ans}."
            except: return None

    # "X plus/times/etc Y" without "what is"
    m2 = _re.search(
        r"^(\S+)\s+(plus|minus|times|multiplied by|divided by|add|subtract)\s+(\S+)$",
        low)
    if m2:
        a = parse_num(m2.group(1))
        b = parse_num(m2.group(3))
        op_str = m2.group(2)
        if a is not None and b is not None:
            try:
                if   "plus"  in op_str or "add" in op_str:        result = a + b
                elif "minus" in op_str or "subtract" in op_str:   result = a - b
                elif "times" in op_str or "multiplied" in op_str: result = a * b
                elif "divided" in op_str:
                    if b == 0: return "You cannot divide by zero."
                    result = a / b
                else: return None
                ri = int(result)
                ans = str(ri) if result == ri else f"{result:.4f}".rstrip("0").rstrip(".")
                return f"That equals {ans}."
            except: return None
    return None

# ── Conversational context builder ────────────────────────────────────────────
def build_seed(user_input, last_exchange, model):
    """
    Build a seed context that includes:
    1. The tail of the last bot reply (conversational memory)
    2. The user's current input
    Replaces any detected name with <NAME> token so the model
    can generalise, then we swap it back at render time.
    """
    s0 = word2idx["<S>"]

    # Words that are NEVER names — feelings, states, common adjectives
    NOT_NAMES = {
        "good","fine","great","okay","ok","tired","sad","happy","bored","well",
        "here","back","done","ready","sure","not","just","also","so","too",
        "the","a","an","is","are","was","be","to","of","in","it","on","at",
        "home","out","up","down","off","away","right","wrong","late","early",
        "busy","free","lost","sick","better","worse","new","old","hot","cold",
        "alive","sorry","confused","excited","nervous","scared","serious",
    }

    detected_name = None
    low = user_input.lower()

    # "my name is X" or "call me X" — always a name
    definite = re.search(r"(?:my name is|call me)\s+([a-z]+)", low)
    if definite:
        candidate = definite.group(1)
        if candidate not in NOT_NAMES:
            detected_name = candidate.capitalize()

    # "i'm X" / "i am X" / "im X" — only a name if X is NOT in our vocab
    # vocab = common English words, so unknown words are likely proper names
    if not detected_name:
        ambiguous = re.search(r"(?:i'm|i am|im)\s+([a-z]+)", low)
        if ambiguous:
            candidate = ambiguous.group(1)
            if candidate not in word2idx and candidate not in NOT_NAMES:
                detected_name = candidate.capitalize()

    if detected_name:
        candidate_low = detected_name.lower()
        user_input = re.sub(
            r'\b' + re.escape(candidate_low) + r'\b',
            "<n>", user_input, flags=re.IGNORECASE
        )

    # tokenise last bot tail + user input
    ctx = [s0] * CTX
    if last_exchange:
        tail = tokenize(last_exchange)[-4:]  # last 4 tokens of bot's previous reply
        for w in tail:
            ctx.append(tok(w))
    for w in tokenize(user_input):
        ctx.append(tok(w))

    return ctx[-CTX:], detected_name

def render(reply, name, model):
    """Swap <n> token back to actual name; drop it silently if no name known.
    Joins contraction tokens (n't, 'm, 's etc.) without spaces.
    Also adds punctuation based on whether the reply is a question or statement."""
    words = reply.split()
    out = []
    for w in words:
        if w == "<n>":
            if name:
                out.append(name)
        else:
            out.append(w)
    if not out:
        return ""
    out[0] = out[0].capitalize()
    # join tokens into string — punctuation attaches without space
    PUNCT = {".", ",", "!", "?", ";"}
    parts = []
    for w in out:
        if w in PUNCT and parts:
            parts[-1] = parts[-1] + w
        else:
            parts.append(w)
    text = " ".join(parts)
    # add punctuation if not already present
    if not text[-1] in ".!?,":
        question_starters = ("what","who","where","when","why","how","is","are",
                              "do","does","did","can","could","would","should",
                              "have","has","will","shall")
        exclaim_words     = ("great","wow","amazing","awesome","wonderful",
                              "fantastic","congrats","congratulations","yay",
                              "excellent","brilliant")
        first = out[0].lower()
        last  = out[-1].lower()
        if first in question_starters:
            text += "?"
        elif any(w in exclaim_words for w in [w.lower() for w in out[:3]]):
            text += "!"
        else:
            text += "."
    return text

# ── Colours ───────────────────────────────────────────────────────────────────
_t = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
R="\033[0m" if _t else ""; B="\033[1m" if _t else ""
CY="\033[96m" if _t else ""; GR="\033[92m" if _t else ""
YL="\033[93m" if _t else ""; DM="\033[2m" if _t else ""
RD="\033[91m" if _t else ""; MG="\033[95m" if _t else ""

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    np.random.seed(42); random.seed(42)

    print(f"\n{B}{CY}┌──────────────────────────────────────────────┐")
    print(f"│  dumbbot v2 🤖  conversational + RL          │")
    print(f"│  pure numpy · no API · learns from YOU       │")
    print(f"│  'stats' for info · 'retrain' to reset       │")
    print(f"│  type 'quit' to exit                         │")
    print(f"└──────────────────────────────────────────────┘{R}\n")

    model = DumbBot()

    if os.path.exists(MODEL_F):
        print(f"{DM}Loading saved model…{R}")
        try:
            model.load(MODEL_F)
            print(f"{GR}Loaded! ({model.feedback_count} feedbacks remembered){R}")
            print(f"{DM}(tip: delete ~/.dumbbot6_model.pkl to force a fresh retrain){R}\n")
        except Exception:
            os.remove(MODEL_F)
            print(f"{YL}Couldn't load saved model — retraining from scratch…{R}\n")
            pretrain(model); model.save(MODEL_F)
    else:
        print(f"{YL}First run — pre-training on dialogue (~25s)…{R}\n")
        pretrain(model)
        model.save(MODEL_F)
        print(f"{GR}Ready! Try: hi  /  my name is [name]  /  how are you{R}\n")

    print(f"{DM}Rate each response:  {GR}y{DM} = good  {RD}n{DM} = bad  {YL}s{DM} = skip{R}\n")

    last_bot_reply = ""

    while True:
        try:
            user = input(f"{GR}{B}You:{R} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DM}Saving… goodbye!{R}")
            model.save(MODEL_F); break

        if not user: continue

        if user.lower() in {"quit","exit","bye","q"}:
            print(f"{CY}{B}Bot:{R} Goodbye! It was really nice talking to you.\n")
            model.save(MODEL_F); break

        if user.lower() == "stats":
            print(f"\n{MG}  Feedback count : {model.feedback_count}")
            print(f"  👍 Good ratings : {model.good_count}")
            print(f"  👎 Bad ratings  : {model.bad_count}")
            print(f"  Known name      : {model.known_name or '(none yet)'}")
            print(f"  Vocab size      : {V} words{R}\n")
            continue

        if user.lower() == "retrain":
            print(f"{YL}Re-running pre-training…{R}\n")
            pretrain(model); model.save(MODEL_F)
            continue

        # ── build context seed ────────────────────────────────────────────
        seed_ctx, detected_name = build_seed(user, last_bot_reply, model)

        if detected_name:
            model.known_name = detected_name
            print(f"  {DM}(remembering your name: {detected_name}){R}")

        # ── generate ──────────────────────────────────────────────────────
        math_ans = try_math(user)
        if math_ans:
            display   = math_ans
            ctxs, ids = [], []
            raw_reply = ""
        else:
            temp  = random.uniform(0.78, 0.95)
            raw_reply, ctxs, ids = model.generate(
                seed_ctx, max_len=random.randint(6, 16), temp=temp
            )
            display = render(raw_reply, model.known_name, model)

        print(f"{CY}{B}Bot:{R} {display}")
        last_bot_reply = raw_reply

        # ── feedback ──────────────────────────────────────────────────────
        try:
            fb = input(f"  {DM}[{GR}y{DM}/{RD}n{DM}/{YL}s{DM}]: {R}").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DM}Saving… goodbye!{R}")
            model.save(MODEL_F); break

        if fb in {"y","yes","good","1","+"}:
            if ctxs:
                model.rl_step(ctxs, ids, reward=+1.0)
            model.feedback_count += 1; model.good_count += 1
            print(f"  {GR}✓ Reinforcing that response{R}\n")
            model.save(MODEL_F)
        elif fb in {"n","no","bad","0","-"}:
            if ctxs:
                model.rl_step(ctxs, ids, reward=-1.0)
            model.feedback_count += 1; model.bad_count += 1
            print(f"  {RD}✗ Discouraging that response{R}\n")
            model.save(MODEL_F)
        else:
            print()

if __name__ == "__main__":
    main()
