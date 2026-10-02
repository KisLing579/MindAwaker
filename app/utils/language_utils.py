import re
from typing import Literal, Optional

LanguageCode = Literal["zh", "en"]

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
_INLINE_FORMULA_RE = re.compile(r"\$([^$]+)\$|\\\((.*?)\\\)")

_LATEX_SPEECH_MAP = {
    "pi": "pi",
    "theta": "theta",
    "alpha": "alpha",
    "beta": "beta",
    "gamma": "gamma",
    "lambda": "lambda",
    "mu": "mu",
    "sigma": "sigma",
    "Delta": "delta",
    "delta": "delta",
    "infty": "infinity",
    "approx": "approximately",
    "le": "less than or equal to",
    "ge": "greater than or equal to",
    "cdot": "times",
    "times": "times",
    "to": "to",
}



def normalize_language(language: Optional[str]) -> Optional[LanguageCode]:
    if not language:
        return None
    lowered = language.lower()
    if lowered.startswith("zh"):
        return "zh"
    if lowered.startswith("en"):
        return "en"
    return None


def detect_language(text: str, fallback: LanguageCode = "zh") -> LanguageCode:
    if not text or not text.strip():
        return fallback

    cjk_count = len(_CJK_RE.findall(text))
    latin_words = len(_LATIN_WORD_RE.findall(text))

    if cjk_count == 0 and latin_words == 0:
        return fallback
    if cjk_count >= max(2, latin_words):
        return "zh"
    if latin_words > 0:
        return "en"
    return fallback


def resolve_language(
    text: str = "",
    requested_language: Optional[str] = None,
    default_language: LanguageCode = "zh",
) -> LanguageCode:
    normalized = normalize_language(requested_language)
    if normalized:
        return normalized
    return detect_language(text, fallback=default_language)


def sanitize_tts_text(text: str, language: Optional[str] = None) -> str:
    raw = str(text or "")
    # Remove line breaks before LaTeX processing can interpret a literal \\n as a command.
    raw = re.sub(r"\\r\\n|\\[nr](?![A-Za-z])|[\r\n]+", " ", raw).strip()
    if not raw.strip():
        return ""

    cleaned = _INLINE_FORMULA_RE.sub(lambda m: (m.group(1) or m.group(2) or "").strip(), raw)
    cleaned = cleaned.replace("$", "")
    cleaned = re.sub(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}", r"\1 over \2", cleaned)
    cleaned = re.sub(r"\\sqrt\s*\{([^{}]+)\}", r"square root of \1", cleaned)

    def _replace_latex_cmd(match: re.Match[str]) -> str:
        cmd = match.group(1)
        return _LATEX_SPEECH_MAP.get(cmd, cmd)

    cleaned = re.sub(r"(?<=[A-Za-z])(?=\\[A-Za-z]+)", " ", cleaned)
    cleaned = re.sub(r"(?<=[A-Za-z])(?=[A-Z])", " ", cleaned)
    cleaned = re.sub(r"\\([A-Za-z]+)", _replace_latex_cmd, cleaned)
    cleaned = cleaned.replace("^", " to the power of ")
    cleaned = cleaned.replace("_", " ")
    cleaned = cleaned.replace("{", " ").replace("}", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def estimate_narration_duration(
    text: str,
    language: Optional[str] = None,
    default_language: LanguageCode = "zh",
    minimum_seconds: float = 3.0,
) -> float:
    resolved_language = resolve_language(text=text, requested_language=language, default_language=default_language)
    cleaned = (text or "").strip()
    if not cleaned:
        return minimum_seconds

    if resolved_language == "en":
        word_count = len(_LATIN_WORD_RE.findall(cleaned))
        estimated = max(word_count / 2.6, len(cleaned) / 18)
    else:
        cjk_count = len(_CJK_RE.findall(cleaned))
        effective_count = cjk_count or len(cleaned)
        estimated = effective_count / 4.5

    return round(max(minimum_seconds, estimated), 2)


def get_default_media_prompt_language(media_model_name: str, requested_language: Optional[str] = None) -> LanguageCode:
    normalized = normalize_language(requested_language)
    if normalized:
        return normalized

    model = (media_model_name or "").lower()
    if any(keyword in model for keyword in ("jimeng", "即梦")):
        return "zh"
    return "en"
