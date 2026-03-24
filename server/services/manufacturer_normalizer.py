import re
from difflib import SequenceMatcher


class ManufacturerNormalizer:
    """Self-contained manufacturer name normalization and matching logic."""

    REMOVABLE_TERMS = {
        "inc", "incorporated", "corp", "corporation", "co", "company", "llc", "l.l.c",
        "ltd", "limited", "gmbh", "s.a.", "s.a", "s.p.a.", "spa", "ag", "kg", "nv",
        "plc", "pty", "pte", "sro", "s.r.o", "srl", "lp", "llp", "pc",
        "products", "product", "brands", "brand", "group", "international", "industries",
        "industry", "mfg", "manufacturing", "manufacturers", "division", "div",
        "usa", "u.s.a", "u.s.", "us", "america", "american", "north", "south",
        "europe", "european", "asia", "pacific",
    }

    def __init__(self):
        self._cache: dict[str, str] = {}
        self._csv_mapping: dict[str, str] = {}
        self._normalized_lookup: dict[str, str] = {}

    def load_mapping(self, csv_mapping: dict[str, str]) -> None:
        """Load the original→root CSV mapping and build a normalised-key lookup."""
        self._csv_mapping = csv_mapping
        self._normalized_lookup = {}
        for original, root in csv_mapping.items():
            norm_key = self.normalize(str(original))
            if norm_key:
                self._normalized_lookup[norm_key] = root

    def normalize(self, name: str) -> str:
        """Return a root-like normalised form of *name*, with caching."""
        if not name:
            return ""
        if name in self._cache:
            return self._cache[name]
        result = self._to_root_form(name)
        self._cache[name] = result
        return result

    def _to_root_form(self, name: str) -> str:
        """Strip legal suffixes/generic terms and return the core token."""
        if not name:
            return ""
        lower = name.lower()
        tokens = re.sub(r"[^0-9a-z]+", " ", lower).split()
        filtered = [t for t in tokens if t not in self.REMOVABLE_TERMS]
        if filtered:
            chosen = filtered[0]
        else:
            alnum_runs = re.findall(r"[0-9a-z]+", lower)
            chosen = alnum_runs[0] if alnum_runs else ""
        return re.sub(r"[^0-9a-z]", "", chosen)

    def matches(self, original: str, website: str, threshold: float = 0.85) -> bool:
        """Return True if *website* manufacturer matches *original*.

        Three strategies in order of reliability:
        1. CSV mapping root containment
        2. Normalized-key lookup
        3. Direct normalised comparison / fuzzy similarity
        """
        if not original or not website:
            return False

        # Strategy 1 – CSV mapping
        root_form = self._csv_mapping.get(original)
        if root_form:
            if self._root_contained_in_website(root_form, website):
                return True
            if self._suffix_stripped_match(original, website):
                return True

        # Strategy 2 – Normalized-key lookup
        if not root_form:
            norm_key = self.normalize(original)
            root_form = self._normalized_lookup.get(norm_key)
            if root_form and self._root_contained_in_website(root_form, website):
                return True

        # Strategy 3 – Direct normalized comparison
        return self._fuzzy_normalized_match(original, website, threshold)

    # ── private helpers ──────────────────────────────────────────────────────

    def _root_contained_in_website(self, root_form: str, website: str) -> bool:
        website_alnum = re.sub(r"[^a-z0-9]", "", website.lower())
        if website_alnum and root_form in website_alnum:
            return True
        norm_website = self.normalize(website)
        if norm_website:
            if root_form in norm_website:
                return True
            if SequenceMatcher(None, root_form, norm_website).ratio() >= 0.85:
                return True
        return False

    def _suffix_stripped_match(self, original: str, website: str) -> bool:
        original_clean = re.sub(
            r'\s+(inc|incorporated|corp|corporation|co|company|llc|ltd|limited'
            r'|products|product|brands|brand)$',
            '', original.lower()
        )
        original_norm = re.sub(r'[-\s]+', ' ', original_clean)
        website_norm = re.sub(r'[-\s]+', ' ', website.lower())
        return original_norm in website_norm

    def _fuzzy_normalized_match(self, original: str, website: str, threshold: float) -> bool:
        norm_original = self.normalize(original)
        norm_website = self.normalize(website)
        if not norm_original or not norm_website:
            return False
        if len(norm_original) >= 3 and len(norm_website) >= 3:
            if norm_original in norm_website or norm_website in norm_original:
                return True
        sim = SequenceMatcher(None, norm_original, norm_website).ratio()
        required = threshold if len(norm_original) >= 4 and len(norm_website) >= 4 else 0.95
        if norm_original == norm_website and len(norm_original) <= 2:
            return False
        return sim >= required
