"""Turns a customer message into a structured request.

Primary path: EURI (structured JSON output, validated by Pydantic).
Fallback path: a deterministic Hinglish-aware rule parser, used only when EURI is unreachable,
not configured, or returns invalid output. The response always says which parser was used.
"""
import logging
import re
from collections import OrderedDict
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.ai.euri_client import EuriClient, EuriError
from app.ai.prompts import PARSE_SCHEMA_HINT, build_parse_messages
from app.schemas import ParserInfo

log = logging.getLogger("kirai.parser")


class ParsedItem(BaseModel):
    name: str
    quantity: int = 1
    category_hint: str | None = None

    @field_validator("quantity", mode="before")
    @classmethod
    def _coerce_qty(cls, v):
        if isinstance(v, str):
            v = v.strip()
        try:
            return int(float(v))
        except (TypeError, ValueError):
            raise ValueError("quantity must be a number") from None


class ParsedRequest(BaseModel):
    intent: Literal["place_order", "check_stock", "low_stock", "other"]
    items: list[ParsedItem] = Field(default_factory=list)
    delivery: bool | None = None
    delivery_address: str | None = None
    language: str | None = None

    @field_validator("intent", mode="before")
    @classmethod
    def _norm_intent(cls, v):
        return str(v).strip().lower().replace(" ", "_")


_CACHE: "OrderedDict[tuple[str, str], ParsedRequest]" = OrderedDict()
_CACHE_MAX = 200


def parse_message(client: EuriClient, message: str) -> tuple[ParsedRequest, ParserInfo]:
    reason = "EURI_API_KEY not configured"
    if client.configured:
        # Temperature-0 parses are deterministic, so a repeated message can reuse the earlier EURI result.
        key = (client.model, " ".join(message.lower().split()))
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key].model_copy(deep=True), ParserInfo(provider="euri", model=client.model, note="cached EURI result")
        try:
            parsed = client.structured_output(build_parse_messages(message), ParsedRequest, PARSE_SCHEMA_HINT)
            parsed.items = [i for i in parsed.items if i.name and i.name.strip()]
            _CACHE[key] = parsed.model_copy(deep=True)
            while len(_CACHE) > _CACHE_MAX:
                _CACHE.popitem(last=False)
            return parsed, ParserInfo(provider="euri", model=client.model)
        except EuriError as exc:
            reason = str(exc)
            log.warning("EURI parse failed, using fallback parser: %s", reason)
        except Exception:  # never let the AI layer take the store down
            reason = "unexpected error while parsing with EURI"
            log.exception(reason)
    return fallback_parse(message), ParserInfo(provider="local", note=reason)


# --------------------------------------------------------------------------- rule-based fallback

NUMBER_WORDS = {
    "ek": 1, "one": 1, "do": 2, "two": 2, "teen": 3, "three": 3, "char": 4, "chaar": 4, "four": 4,
    "paanch": 5, "panch": 5, "five": 5, "chhe": 6, "che": 6, "six": 6, "saat": 7, "seven": 7,
    "aath": 8, "eight": 8, "nau": 9, "nine": 9, "das": 10, "ten": 10, "dozen": 12, "darjan": 12,
}
VERBS = {"bhej", "bhejo", "bhejna", "de", "dena", "kar", "karo", "le", "lao", "add", "order", "dedo", "send", "get", "give"}
STOP = {
    "bhaiya", "bhaiyya", "bhai", "bhaisahab", "sir", "please", "pls", "plz", "mujhe", "muje", "mere", "meri", "mera",
    "hume", "humko", "ghar", "pe", "par", "ko", "se", "deliver", "delivery", "home", "kar", "karna", "karo", "karke",
    "dena", "dedo", "do", "de", "bhej", "bhejo", "bhejna", "bhijwa", "bhijwana", "chahiye", "chahie", "chaiye",
    "order", "add", "lao", "laao", "lena", "le", "liye", "hai", "hain", "hi", "bhi", "to", "toh", "nahi", "kya",
    "kaun", "kitna", "kitne", "kitni", "ho", "gaya", "gayi", "gaye", "khatam", "stock", "available", "check",
    "show", "bata", "batao", "bataiye", "dikhao", "dikha", "mein", "main", "me", "aap", "aapke", "tumhare",
    "abhi", "jaldi", "and", "or", "with", "i", "want", "need", "would", "like", "can", "could", "you", "get",
    "send", "my", "is", "are", "it", "there", "any", "left", "have", "what", "price", "rate", "cost", "bhav",
    "for", "in", "at", "on", "this", "that", "address", "location", "milega", "mil", "sakta", "sakte", "kijiye",
    "kijiyega", "hoga", "chahiyo", "thoda", "give", "us", "me", "packet", "packets", "pkt", "pkts", "pack",
    "packs", "pouch", "bottle", "bottles", "piece", "pieces", "pc", "pcs", "dabba", "litre", "liter", "ltr", "l",
    "kg", "gm", "gram", "grams", "g", "ml", "of", "the", "a", "an", "some", "ka", "ki", "ke", "wala", "wali",
    "ab", "wo", "woh", "ye", "yeh", "koi", "aur", "unko", "usko", "mera", "hamare", "hamara", "tak", "ne",
}
DELIVERY_WORDS = re.compile(r"deliver|delivery|ghar|home|bhej|bhijwa|send")
PICKUP_WORDS = re.compile(r"pick ?up|khud aa|aake le|aa ke le|aakar le|store se le|dukaan se le|take away")
ORDER_WORDS = re.compile(r"\b(bhej|bhejo|bhejna|dena|dedo|de do|chahiye|chahie|chaiye|order|add|lao|laao|send|deliver|want|need|get me|give me|bhijwa)")
CHECK_WORDS = re.compile(r"stock|available|availability|khatam|hai kya|kitna|kitne|price|rate|bhav|cost|how much|milega|check|left")
LOW_STOCK = re.compile(r"low stock|running low|kam stock|stock kam|khatam hone|running out|out of stock items|what.*(low|finish|running out)|which.*(low|finish|out)")
GREETING = re.compile(r"^(hi|hello|hey|namaste|namaskar|hii+|thanks|thank you|dhanyavad|shukriya|good (morning|evening|afternoon))\b")
CATEGORY_HINTS = {
    "oreo": "biscuits", "bourbon": "biscuits", "marie": "biscuits", "cookie": "biscuits", "cookies": "biscuits",
    "hide": "biscuits", "pringles": "chips", "sprite": "cold drinks", "fanta": "cold drinks",
    "mirinda": "cold drinks", "7up": "cold drinks", "limca": "cold drinks", "mazza": "cold drinks",
    "frooti": "cold drinks", "bisleri": "cold drinks",
}
TOKEN_RE = re.compile(r"\d+(?:\.\d+)?x?[a-z]*|[a-z']+")


def _split_segments(text: str) -> list[str]:
    segments: list[str] = []
    for sentence in re.split(r"[.!?\n;]+", text):
        segments.extend(re.split(r",|&|\+|\baur\b|\band\b", sentence))
    return [s.strip() for s in segments if s.strip()]


def _parse_segment(segment: str) -> tuple[ParsedItem, bool] | None:
    """Returns (item, quantity_was_explicit) or None when the segment names no product."""
    tokens = TOKEN_RE.findall(segment.replace("’", "'"))
    qty: int | None = None
    keep: list[str] = []
    for i, tok in enumerate(tokens):
        plain = tok.replace("'", "")
        if re.fullmatch(r"\d+x?", plain):
            if qty is None:
                qty = int(plain.rstrip("x"))
            continue
        if re.fullmatch(r"\d+\.\d+", plain):
            continue
        if tok in NUMBER_WORDS and qty is None:
            if tok == "do":  # "do" is either the number 2 or the verb ("bhej do")
                prev = tokens[i - 1] if i > 0 else None
                nxt = tokens[i + 1] if i + 1 < len(tokens) else None
                if prev in VERBS or nxt is None or nxt in STOP:
                    continue
            qty = NUMBER_WORDS[tok]
            continue
        if tok in STOP:
            continue
        keep.append(plain)
    if not keep:
        return None
    hint = next((CATEGORY_HINTS[t] for t in keep if t in CATEGORY_HINTS), None)
    item = ParsedItem(name=" ".join(keep), quantity=qty if qty is not None else 1, category_hint=hint)
    return item, qty is not None


def fallback_parse(message: str) -> ParsedRequest:
    text = message.lower().strip()
    parsed = [p for seg in _split_segments(text) if (p := _parse_segment(seg))]
    items = [item for item, _ in parsed]
    explicit_qty = any(flag for _, flag in parsed)

    delivery: bool | None = None
    if PICKUP_WORDS.search(text):
        delivery = False
    elif DELIVERY_WORDS.search(text):
        delivery = True

    if LOW_STOCK.search(text):
        return ParsedRequest(intent="low_stock", delivery=None, language="hinglish")
    has_order_verb = bool(ORDER_WORDS.search(text))
    if GREETING.search(text) and not has_order_verb and not explicit_qty:
        return ParsedRequest(intent="other", language="english")
    if CHECK_WORDS.search(text) and not has_order_verb:
        return ParsedRequest(intent="check_stock", items=items, language="hinglish")
    # Only place an order on an explicit signal (an order verb or a quantity).
    if has_order_verb or (items and explicit_qty):
        return ParsedRequest(intent="place_order", items=items, delivery=delivery, language="hinglish")
    if items:  # a bare product name ("Maggi?") is safest treated as a read-only stock lookup
        return ParsedRequest(intent="check_stock", items=items, language="hinglish")
    return ParsedRequest(intent="other")
