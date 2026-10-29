"""Épuration en mots-clés : noms, verbes à l'infinitif, adjectifs et nombres (spaCy, hors ligne)."""

MODEL = "fr_core_news_md"
KEPT = {"NOUN", "PROPN", "VERB", "ADJ", "NUM"}  # sans auxiliaires (a présenté → présenter), articles, pronoms…
EMPTY_VERBS = {"être", "avoir"}  # même employés seuls (« vous y êtes »), ils ne disent rien du sujet


class Condenser:
    def __init__(self, model: str = MODEL):
        import spacy

        self._nlp = spacy.load(model, disable=["parser", "ner"])  # seuls la nature des mots et le lemme servent

    def __call__(self, text: str) -> str:
        words: list[str] = []
        glue = False  # spaCy coupe « centres-villes » en trois : on recolle autour du trait d'union
        for t in self._nlp(text):
            if t.text == "-" and words and not t.whitespace_ and t.i and not t.nbor(-1).whitespace_:
                glue = True
                continue
            if t.pos_ in KEPT and t.lemma_ not in EMPTY_VERBS and any(c.isalnum() for c in t.text):
                word = t.lemma_ if t.pos_ == "VERB" else t.text
                if glue:
                    words[-1] += "-" + word
                else:
                    words.append(word)
            glue = False
        return " ".join(words)
