from gui.i18n import STRINGS_EN, STRINGS_KO


class UIStrings:
    """Centralized UI Text Strings and Dictionary-Based i18n for IBQtools."""

    CURRENT_LANG = "en"  # Default language: "en" or "ko"

    _STRINGS = {
        "en": STRINGS_EN,
        "ko": STRINGS_KO,
    }

    @classmethod
    def get(cls, key: str, default: str = "") -> str:
        """Retrieves localized text for given key with fallback to English or default."""
        lang = cls.CURRENT_LANG
        res = cls._STRINGS.get(lang, {}).get(key)
        if res is not None:
            return res
        res_en = cls._STRINGS.get("en", {}).get(key)
        if res_en is not None:
            return res_en
        return default or key
