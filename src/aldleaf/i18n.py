"""Language support: book-language detection, multilingual layout keywords, the
labels Aldleaf writes into an EPUB, and a quality check of the PDF's text layer.

Supported: horizontal books in left-to-right scripts, including Latin, Greek,
Cyrillic, the Indic scripts (Devanagari, Gurmukhi, Bengali, Tamil, Telugu,
Kannada, Malayalam, Gujarati, Odia, Sinhala), Thai, Chinese (Simplified and
Traditional), Japanese and Korean. Book text is never translated: only the few
labels Aldleaf adds (contents heading, cover title, byline prefix, page markers)
follow the book's language.

Not supported yet: right-to-left scripts (Arabic, Hebrew, Persian, Urdu) and
vertical Chinese or Japanese text. Both are detected and refused with a clear message.
"""
import collections
import re
import unicodedata

# ---------------------------------------------------------------- scripts
# (name, first, last, default language)
SCRIPTS = [
    ("Latin", 0x0041, 0x024F, None), ("Greek", 0x0370, 0x03FF, "el"), ("Cyrillic", 0x0400, 0x04FF, None),
    ("Armenian", 0x0530, 0x058F, "hy"), ("Hebrew", 0x0590, 0x05FF, "he"), ("Arabic", 0x0600, 0x06FF, "ar"),
    ("Arabic", 0x0750, 0x077F, "ar"), ("Arabic", 0xFB50, 0xFDFF, "ar"), ("Arabic", 0xFE70, 0xFEFF, "ar"),
    ("Devanagari", 0x0900, 0x097F, None), ("Bengali", 0x0980, 0x09FF, "bn"), ("Gurmukhi", 0x0A00, 0x0A7F, "pa"),
    ("Gujarati", 0x0A80, 0x0AFF, "gu"), ("Odia", 0x0B00, 0x0B7F, "or"), ("Tamil", 0x0B80, 0x0BFF, "ta"),
    ("Telugu", 0x0C00, 0x0C7F, "te"), ("Kannada", 0x0C80, 0x0CFF, "kn"), ("Malayalam", 0x0D00, 0x0D7F, "ml"),
    ("Sinhala", 0x0D80, 0x0DFF, "si"), ("Thai", 0x0E00, 0x0E7F, "th"), ("Lao", 0x0E80, 0x0EFF, "lo"),
    ("Myanmar", 0x1000, 0x109F, "my"), ("Georgian", 0x10A0, 0x10FF, "ka"), ("Hangul", 0x1100, 0x11FF, "ko"),
    ("Khmer", 0x1780, 0x17FF, "km"), ("Kana", 0x3040, 0x30FF, "ja"), ("Hangul", 0x3130, 0x318F, "ko"),
    ("Han", 0x3400, 0x4DBF, None), ("Han", 0x4E00, 0x9FFF, None), ("Hangul", 0xAC00, 0xD7AF, "ko"),
    ("Han", 0xF900, 0xFAFF, None),
]
RTL_SCRIPTS = {"Hebrew", "Arabic"}
# scripts written without spaces between words: lines join without a space
NO_SPACE_SCRIPTS = {"Han", "Kana", "Thai", "Lao", "Khmer", "Myanmar", "CJKPunct"}


def script_of(ch):
    o = ord(ch)
    if 0x3000 <= o <= 0x303F or 0xFF00 <= o <= 0xFFEF:
        return "CJKPunct"
    for name, a, b, _ in SCRIPTS:
        if a <= o <= b:
            return name
    return None


def joins_without_space(prev_char, next_char):
    """True when a line break between these characters needs no space (CJK, Thai, ...)."""
    return script_of(prev_char) in NO_SPACE_SCRIPTS and script_of(next_char) in NO_SPACE_SCRIPTS


def script_counts(text):
    c = collections.Counter()
    for ch in text:
        if ch.isspace() or not (ch.isalpha() or unicodedata.category(ch).startswith("M")):
            continue
        s = script_of(ch)
        if s:
            c[s] += 1
    return c


# ---------------------------------------------------------------- detection by words
STOPWORDS = {
    "en": "the and of to a in that is was he she it for with as his her on at by had not but from they you which".split(),
    "de": "der die und das ist nicht ein eine zu den mit sich des auf für im dem war sie er es auch als noch nach wie".split(),
    "fr": "le la les et des est une un que qui pas dans pour sur au avec il elle ne se du sont mais nous vous était".split(),
    "es": "el la los las y de que en un una es por con no para se del al lo como pero sus fue estaba".split(),
    "pt": "o a os as e de que em um uma para com não do da no na se por mas foi ela ele estava".split(),
    "it": "il la che di e un una per non con sono del della gli le ma si nel alla era anche".split(),
    "nl": "de het een en van is dat niet op te zijn met voor als maar ook hij zij was bij".split(),
    "sv": "och att det som en på är av för med till den har inte jag var men om ett hon han".split(),
    "da": "og at det som en på er af for med til den har ikke jeg var men om et hun han".split(),
    "nb": "og at det som en på er av for med til den har ikke jeg var men om et hun han ble".split(),
    "fi": "ja on ei se että oli hän mutta kun niin kuin jo vain olla myös joka tai".split(),
    "pl": "i w nie na że się z do to jest jak po ale co tak za od jego była".split(),
    "cs": "a v se na že je to s z do jako ale by jsem po o pro byla".split(),
    "ro": "și de în la cu nu se că o un pe din a era ca mai".split(),
    "hu": "a az és hogy nem is egy meg de csak ki van volt már".split(),
    "tr": "ve bir bu da de için ile ne çok gibi o ama daha onu".split(),
    "ru": "и в не на что я с он как это по но из у за так же от была".split(),
    "uk": "і в не на що я з він як це по але у за та від була".split(),
    "hi": "है और का की के में से को यह था थी नहीं पर भी एक".split(),
    "mr": "आहे आणि च्या ची चा ला ने होते हे या मी तो ती".split(),
    "ne": "छ र को मा ले थियो पनि यो एक गर्न हो".split(),
}
TRADITIONAL = set("這們說書個來時為學國會長開間關點與後對從裡還讓經見東車門風飛馬鳥魚麼樣條聽語讀寫")
SIMPLIFIED = set("这们说书个来时为学国会长开间关点与后对从里还让经见东车门风飞马鸟鱼么样条听语读写")
_TOKEN = re.compile(r"[^\s.,;:!?।॥\"'()\[\]“”‘’«»—–\-0-9]+")   # keeps Indic vowel signs inside words


# letters only one language (among the ones above) uses: a strong hint in short samples
_LETTERS = {"pl": "łąęśźż", "cs": "ěřů", "ro": "ăîșț", "hu": "őű", "tr": "ğı", "pt": "ãõ", "es": "ñ¿¡",
            "fr": "œ", "de": "ß"}


def _by_stopwords(words, langs):
    counts = collections.Counter(words)
    n = max(len(words), 1)
    letters = collections.Counter("".join(words))
    scores = {l: (sum(counts[w] for w in STOPWORDS[l]) + 0.5 * sum(letters[c] for c in _LETTERS.get(l, ""))) / n
              for l in langs}
    best = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    if not best:
        return None
    (lang, top), second = best[0], (best[1][1] if len(best) > 1 else 0)
    if top < 0.05 or top < second * 1.15:
        return None
    return lang


# Danish and Norwegian Bokmål share most short words; these tell them apart.
_NORDIC = {
    "da": "af blev efter hvad mig sig nu havde ud kun meget hvor skulle sagde noget aldrig tændtes lygten".split(),
    "nb": "av ble etter hva meg seg nå hadde ut bare mye hvor skulle sa noe aldri ble lykten".split(),
    "sv": "och är inte jag hon han var att det som av för med till hade blev efter nu sig mig vad aldrig".split(),
}


def _nordic(words):
    c = collections.Counter(words)
    shared = {"og", "at", "det", "som", "en", "på", "er", "for", "med", "til", "den", "har", "ikke", "jeg",
              "var", "men", "om", "et", "hun", "han"}
    if sum(c[w] for w in shared) < len(words) * 0.04 and sum(c[w] for w in _NORDIC["sv"]) < len(words) * 0.04:
        return None
    score = {l: sum(c[w] for w in ws) for l, ws in _NORDIC.items()}
    best = max(score, key=score.get)
    return best if score[best] > 0 else None


def detect_language(doc, sample_text):
    """Return (bcp47_code, how): how is 'pdf' (declared in the PDF), 'text'
    (worked out from the script and words) or 'default' (could not tell; English)."""
    try:
        cat = doc.pdf_catalog()
        kind, val = doc.xref_get_key(cat, "Lang")
        if kind == "string" and re.match(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$", val or ""):
            return val, "pdf"
    except Exception:
        pass
    sc = script_counts(sample_text[:200000])
    if sum(sc.values()) < 20:
        return "en", "default"
    script = sc.most_common(1)[0][0]
    if script == "Han" and sc.get("Kana", 0) > sc["Han"] * 0.05:
        script = "Kana"
    default = {name: lang for name, a, b, lang in SCRIPTS}
    if script == "Han":
        t = sum(1 for ch in sample_text if ch in TRADITIONAL)
        s = sum(1 for ch in sample_text if ch in SIMPLIFIED)
        return ("zh-Hant" if t > s else "zh-Hans"), "text"
    if default.get(script):
        return default[script], "text"
    words = [w.lower() for w in _TOKEN.findall(sample_text)][:20000]
    pool = {"Latin": ["en", "de", "fr", "es", "pt", "it", "nl", "sv", "da", "nb", "fi", "pl", "cs", "ro", "hu", "tr"],
            "Cyrillic": ["ru", "uk"], "Devanagari": ["hi", "mr", "ne"]}.get(script, [])
    lang = _by_stopwords(words, pool)
    if lang in ("da", "nb", "sv") or (script == "Latin" and lang is None):
        lang = _nordic(words) or lang
    if lang:
        return lang, "text"
    return {"Devanagari": ("hi", "text"), "Cyrillic": ("ru", "text")}.get(script, ("en", "default"))


def unsupported_layout(text, vertical_chars, total_chars):
    """A reason string if the book can't be converted yet, else None."""
    sc = script_counts(text[:200000])
    letters = sum(sc.values())
    if letters and sum(sc[s] for s in RTL_SCRIPTS) > letters * 0.3:
        return ("This book is written in a right-to-left script (Arabic, Hebrew, Persian or Urdu). "
                "Aldleaf doesn't support right-to-left books yet.")
    if total_chars and vertical_chars > total_chars * 0.3:
        return ("This book uses vertical text (vertical Chinese or Japanese). "
                "Aldleaf only supports horizontal text for now.")
    return None


# ---------------------------------------------------------------- text-layer quality
_SIGN_CLASS = ("ा-ौা-ৌਾ-ੌા-ૌା-ୌ"
               "ா-ௌా-ౌಾ-ೌാ-ൌා-ෟ")
_INDIC_SIGNS = re.compile(f"[{_SIGN_CLASS}]")
# every combining mark of the Indic blocks (vowel signs, anusvara, chandrabindu, visarga, addak, nukta, virama)
_INDIC_MARKS = "".join(chr(c) for c in range(0x0900, 0x0E00) if unicodedata.category(chr(c)).startswith("M"))
_DOUBLE_SIGN = re.compile("([" + re.escape(_INDIC_MARKS) + "])\\1")
_INDIC_RANGE = "ऀ-෿"


def repair_text_layer(t):
    """Safe repairs only: a doubled identical vowel sign (never valid spelling;
    a common fault in PDFs with conjunct ligatures) becomes a single one."""
    return _DOUBLE_SIGN.sub(r"\1", t)


def text_layer_issues(text):
    """Signs that the PDF's hidden text is damaged (what you copy differs from what
    you see). Returns (count, examples). Only flags patterns that can't be real text."""
    bad, examples = 0, []
    for w in re.findall(r"\S+", text):
        reason = None
        if "�" in w or any(0xE000 <= ord(c) <= 0xF8FF for c in w):
            reason = "unreadable characters"
        elif re.search(f"[{_INDIC_RANGE}]", w):
            core = w.strip(".,;:!?।॥\"'()[]“”‘’«»-")
            if re.search(f"[{_INDIC_RANGE}][Ā-ʯ]|[Ā-ʯ][{_INDIC_RANGE}]", core):
                reason = "stray symbols inside a word"
            elif core and _INDIC_SIGNS.match(core):
                reason = "vowel sign without a letter"
        if reason:
            bad += 1
            if len(examples) < 8:
                examples.append(f"{w} ({reason})")
    return bad, examples


# ---------------------------------------------------------------- layout keywords
_NUM = (r"[0-9IVXLCDMivxlcdm०-९০-৯੦-੯૦-૯௦-௯๐-๙"
        r"０-９一二三四五六七八九十百千〇零两兩]+")
CHAPTER_WORDS = ("chapter|part|book|act|section|prologue|epilogue|"
                 "kapitel|teil|buch|akt|abschnitt|prolog|epilog|"
                 "chapitre|partie|livre|acte|épilogue|"
                 "capítulo|capitulo|parte|libro|acto|prólogo|epílogo|livro|"
                 "capitolo|atto|prologo|epilogo|"
                 "hoofdstuk|deel|boek|"
                 "kapittel|del|bok|"
                 "luku|osa|"
                 "rozdział|część|księga|kapitola|část|"
                 "capitolul|partea|"
                 "глава|часть|книга|розділ|частина|"
                 "κεφάλαιο|μέρος|"
                 "अध्याय|प्रकरण|भाग|ਅਧਿਆਇ|ਕਾਂਡ|ਭਾਗ|অধ্যায়|পরিচ্ছেদ|পর্ব|அத்தியாயம்|பகுதி|"
                 "บทที่|ตอนที่")
CHAPTER_LABEL = re.compile(
    rf"^(?:(?:{CHAPTER_WORDS})\s*{_NUM}\.?|{_NUM}\.?\s*(?:fejezet|bölüm|rész|kısım|kapitola|luku)"
    rf"|第\s*{_NUM}\s*[章节節回部卷篇话話]|제\s*{_NUM}\s*[장부편화])$", re.I)

# "By", "De", "Di", "Da", "Par", "Por"... are also ordinary words ("By the Sea",
# "De signalen"). Without a colon they only start a byline when a name follows.
_BY_AMBIGUOUS = r"by|von|de|par|por|di|da|door|av|af|od"
_BY_SURE = (r"przez|kirjoittanut|írta|yazan|"
            r"autor|автор|του|της|συγγραφέας|लेखक|लेखिका|ਲੇਖਕ|লেখক|ஆசிரியர்|โดย|作者|著者|著|作|지은이|글")
_UPPER = "A-ZÀ-ÖØ-ÞĀĂĄĆČĎĐĒĘĚĞİŁŃŇŐŒŘŚŞŠŢŤŰŸŹŻŽΑ-ΩΆ-Ώ\u0400-\u042F"
_BY = (rf"(?:(?i:{_BY_SURE})\s*[:：\s]|(?i:{_BY_AMBIGUOUS})\s*[:：]|(?i:{_BY_AMBIGUOUS})\s+(?=[{_UPPER}]))")
BYLINE_WORDS = _BY_AMBIGUOUS + "|" + _BY_SURE
BYLINE = re.compile(rf"^\s*{_BY}\s*\S")
BYLINE_CAPTURE = re.compile(rf"^\s*{_BY}\s*(.+)$")

_WARN_PHRASES = {
    "trigger warning", "trigger warnings", "content warning", "content warnings", "content note", "content notes",
    "inhaltswarnung", "inhaltswarnungen", "triggerwarnung", "triggerwarnungen",
    "avertissement", "avertissements", "avertissement de contenu", "avertissements de contenu",
    "advertencia", "advertencias", "advertencia de contenido", "advertencias de contenido",
    "aviso de conteúdo", "avisos de conteúdo", "aviso de gatilho", "avisos de gatilho",
    "avvertenza", "avvertenze", "avvertenze sui contenuti", "avvisi sui contenuti",
    "inhoudswaarschuwing", "inhoudswaarschuwingen", "triggerwaarschuwing", "triggerwaarschuwingen",
    "innehållsvarning", "innehållsvarningar", "triggervarning", "triggervarningar",
    "indholdsadvarsel", "indholdsadvarsler", "innholdsadvarsel", "innholdsadvarsler",
    "sisältövaroitus", "sisältövaroitukset", "ostrzeżenie", "ostrzeżenia", "ostrzeżenia o treści",
    "upozornění", "upozornění na obsah", "avertisment", "avertismente", "tartalmi figyelmeztetés",
    "içerik uyarısı", "içerik uyarıları", "предупреждение", "предупреждения", "попередження",
    "προειδοποίηση", "προειδοποιήσεις", "चेतावनी", "सामग्री चेतावनी", "ਚੇਤਾਵਨੀ", "সতর্কতা",
    "எச்சரிக்கை", "คำเตือน", "内容警告", "內容警告", "注意", "内容に関する注意", "콘텐츠 경고", "주의",
}


class _WarnHdr:
    def match(self, t):
        key = t.strip().rstrip(":：").strip().casefold().replace("\u0307", "")   # Turkish İ -> i
        return key in _WARN_KEYS


_WARN_KEYS = {w.casefold() for w in _WARN_PHRASES}   # Greek final ς -> σ
WARN_HDR = _WarnHdr()

# ---------------------------------------------------------------- e-mail headers printed in books
EMAIL_FROM_WORDS = "From|Von|De|Da|Van|Från|Fra|Od|От|Lähettäjä|Feladó|Kimden"
EMAIL_FIELD_WORDS = (EMAIL_FROM_WORDS + "|Sent|To|Cc|CC|Bcc|Subject|Date|"
                     "Gesendet|An|Betreff|Datum|Envoyé|À|A|Objet|Enviado|Para|Asunto|Fecha|"
                     "Inviato|Oggetto|Data|Verzonden|Aan|Onderwerp|Assunto|Skickat|Till|Ämne|"
                     "Sendt|Til|Emne|Wysłano|Do|Temat|Отправлено|Кому|Тема|Lähetetty|Vastaanottaja|Aihe|"
                     "Elküldve|Címzett|Tárgy|Gönderildi|Kime|Konu")
EMAIL_HDR = re.compile(rf"^({EMAIL_FIELD_WORDS}):")
EMAIL_HDR_SPACE = re.compile(rf"^({EMAIL_FIELD_WORDS}):\s")
EMAIL_FROM = re.compile(rf"^({EMAIL_FROM_WORDS}):")

# ---------------------------------------------------------------- labels written into the EPUB
_KEYS = ("page", "titlepage", "start", "contents", "cover", "copyright", "by", "scene_break", "warnings",
         "licensed", "licensed_short")
_L = {
    "en": ("Page", "Title page", "Start", "Contents", "Cover", "Copyright", "By", "Scene break", "Content warnings",
           "Licensed to {who} (purchased {when})", "Licensed to {who}"),
    "de": ("Seite", "Titelseite", "Beginn", "Inhalt", "Cover", "Impressum", "Von", "Szenenwechsel", "Inhaltswarnungen",
           "Lizenziert für {who} (gekauft {when})", "Lizenziert für {who}"),
    "fr": ("Page", "Page de titre", "Début", "Table des matières", "Couverture", "Mentions légales", "Par",
           "Changement de scène", "Avertissements", "Licence accordée à {who} (achat du {when})", "Licence accordée à {who}"),
    "es": ("Página", "Portadilla", "Inicio", "Índice", "Cubierta", "Créditos", "Por", "Cambio de escena",
           "Advertencias de contenido", "Con licencia para {who} (comprado el {when})", "Con licencia para {who}"),
    "pt": ("Página", "Folha de rosto", "Início", "Sumário", "Capa", "Ficha técnica", "Por", "Mudança de cena",
           "Avisos de conteúdo", "Licenciado para {who} (comprado em {when})", "Licenciado para {who}"),
    "it": ("Pagina", "Frontespizio", "Inizio", "Indice", "Copertina", "Colophon", "Di", "Cambio di scena",
           "Avvertenze sui contenuti", "Concesso in licenza a {who} (acquistato il {when})", "Concesso in licenza a {who}"),
    "nl": ("Pagina", "Titelpagina", "Begin", "Inhoud", "Omslag", "Colofon", "Door", "Scènewissel",
           "Inhoudswaarschuwingen", "In licentie gegeven aan {who} (gekocht {when})", "In licentie gegeven aan {who}"),
    "sv": ("Sida", "Titelsida", "Början", "Innehåll", "Omslag", "Copyright", "Av", "Scenbyte", "Innehållsvarningar",
           "Licensierad till {who} (köpt {when})", "Licensierad till {who}"),
    "da": ("Side", "Titelside", "Start", "Indhold", "Omslag", "Kolofon", "Af", "Sceneskift", "Indholdsadvarsler",
           "Licenseret til {who} (købt {when})", "Licenseret til {who}"),
    "nb": ("Side", "Tittelside", "Start", "Innhold", "Omslag", "Kolofon", "Av", "Sceneskift", "Innholdsadvarsler",
           "Lisensiert til {who} (kjøpt {when})", "Lisensiert til {who}"),
    "fi": ("Sivu", "Nimiösivu", "Alku", "Sisällys", "Kansi", "Tekijänoikeudet", "Kirjoittanut", "Kohtauksen vaihto",
           "Sisältövaroitukset", "Lisensoitu käyttäjälle {who} (ostettu {when})", "Lisensoitu käyttäjälle {who}"),
    "pl": ("Strona", "Strona tytułowa", "Początek", "Spis treści", "Okładka", "Prawa autorskie", "Autor:", "Zmiana sceny",
           "Ostrzeżenia o treści", "Licencja dla {who} (zakup {when})", "Licencja dla {who}"),
    "cs": ("Strana", "Titulní strana", "Začátek", "Obsah", "Obálka", "Tiráž", "Autor:", "Změna scény",
           "Upozornění na obsah", "Licencováno pro {who} (zakoupeno {when})", "Licencováno pro {who}"),
    "ro": ("Pagina", "Pagina de titlu", "Început", "Cuprins", "Copertă", "Drepturi de autor", "De", "Schimbare de scenă",
           "Avertismente", "Licențiat pentru {who} (cumpărat {when})", "Licențiat pentru {who}"),
    "hu": ("Oldal", "Címoldal", "Kezdet", "Tartalom", "Borító", "Impresszum", "Írta", "Jelenetváltás",
           "Tartalmi figyelmeztetések", "Licenc: {who} (vásárlás: {when})", "Licenc: {who}"),
    "tr": ("Sayfa", "Başlık sayfası", "Başlangıç", "İçindekiler", "Kapak", "Künye", "Yazan:", "Sahne geçişi",
           "İçerik uyarıları", "{who} adına lisanslı (satın alma: {when})", "{who} adına lisanslı"),
    "el": ("Σελίδα", "Σελίδα τίτλου", "Αρχή", "Περιεχόμενα", "Εξώφυλλο", "Πνευματικά δικαιώματα", "Συγγραφέας:",
           "Αλλαγή σκηνής", "Προειδοποιήσεις περιεχομένου", "Άδεια για {who} (αγορά {when})", "Άδεια για {who}"),
    "ru": ("Страница", "Титульный лист", "Начало", "Содержание", "Обложка", "Выходные данные", "Автор:", "Смена сцены",
           "Предупреждения", "Лицензия: {who} (куплено {when})", "Лицензия: {who}"),
    "uk": ("Сторінка", "Титульна сторінка", "Початок", "Зміст", "Обкладинка", "Вихідні дані", "Автор:", "Зміна сцени",
           "Попередження", "Ліцензія: {who} (придбано {when})", "Ліцензія: {who}"),
    "hi": ("पृष्ठ", "मुखपृष्ठ", "आरंभ", "विषय-सूची", "आवरण", "कॉपीराइट", "लेखक:", "दृश्य परिवर्तन", "सामग्री चेतावनी",
           "{who} के लिए लाइसेंस ({when} को खरीदा)", "{who} के लिए लाइसेंस"),
    "mr": ("पृष्ठ", "शीर्षक पृष्ठ", "सुरुवात", "अनुक्रमणिका", "मुखपृष्ठ", "प्रताधिकार", "लेखक:", "दृश्य बदल", "सामग्री सूचना",
           "{who} साठी परवाना ({when} रोजी खरेदी)", "{who} साठी परवाना"),
    "pa": ("ਪੰਨਾ", "ਸਿਰਲੇਖ ਪੰਨਾ", "ਸ਼ੁਰੂ", "ਤਤਕਰਾ", "ਕਵਰ", "ਕਾਪੀਰਾਈਟ", "ਲੇਖਕ:", "ਦ੍ਰਿਸ਼ ਬਦਲਾਅ", "ਸਮੱਗਰੀ ਚੇਤਾਵਨੀ",
           "{who} ਲਈ ਲਾਇਸੈਂਸ ({when} ਨੂੰ ਖਰੀਦਿਆ)", "{who} ਲਈ ਲਾਇਸੈਂਸ"),
    "bn": ("পৃষ্ঠা", "শিরোনাম পৃষ্ঠা", "শুরু", "সূচিপত্র", "প্রচ্ছদ", "স্বত্ব", "লেখক:", "দৃশ্য পরিবর্তন", "বিষয়বস্তু সতর্কতা",
           "{who}-এর জন্য লাইসেন্স ({when} কেনা)", "{who}-এর জন্য লাইসেন্স"),
    "ta": ("பக்கம்", "தலைப்புப் பக்கம்", "தொடக்கம்", "பொருளடக்கம்", "அட்டை", "பதிப்புரிமை", "ஆசிரியர்:", "காட்சி மாற்றம்",
           "உள்ளடக்க எச்சரிக்கை", "{who} க்கான உரிமம் ({when} வாங்கப்பட்டது)", "{who} க்கான உரிமம்"),
    "th": ("หน้า", "หน้าชื่อเรื่อง", "เริ่มต้น", "สารบัญ", "ปก", "ลิขสิทธิ์", "โดย", "เปลี่ยนฉาก", "คำเตือนเนื้อหา",
           "อนุญาตให้ {who} (ซื้อเมื่อ {when})", "อนุญาตให้ {who}"),
    "ja": ("{n}ページ", "扉", "本文", "目次", "表紙", "奥付", "著者：", "場面転換", "内容に関する注意",
           "{who} にライセンス（{when} 購入）", "{who} にライセンス"),
    "zh-hans": ("第{n}页", "扉页", "正文", "目录", "封面", "版权页", "作者：", "场景转换", "内容警告",
                "授权给 {who}（{when} 购买）", "授权给 {who}"),
    "zh-hant": ("第{n}頁", "扉頁", "正文", "目錄", "封面", "版權頁", "作者：", "場景轉換", "內容警告",
                "授權給 {who}（{when} 購買）", "授權給 {who}"),
    "ko": ("{n}쪽", "속표지", "본문", "차례", "표지", "판권", "지은이:", "장면 전환", "콘텐츠 경고",
           "{who}에게 라이선스 ({when} 구매)", "{who}에게 라이선스"),
}
LABELS = {k: dict(zip(_KEYS, v)) for k, v in _L.items()}


def labels(lang):
    """Labels for a BCP 47 language tag; falls back to English."""
    tag = (lang or "en").lower()
    if tag.startswith("zh"):
        return LABELS["zh-hant" if ("hant" in tag or tag in ("zh-tw", "zh-hk", "zh-mo")) else "zh-hans"]
    if tag.split("-")[0] == "no":
        return LABELS["nb"]
    return LABELS.get(tag.split("-")[0], LABELS["en"])


def page_label(lab, n):
    """'Page 5', 'Seite 5', '第5页', '5쪽' ..."""
    p = lab["page"]
    return p.format(n=n) if "{n}" in p else f"{p} {n}"


def byline_text(lab, author):
    """'By Ada Example', 'Von Ada Beispiel', '作者：山田' ..."""
    by = lab["by"]
    return f"{by}{author}" if by.endswith("：") else f"{by} {author}"


# ---------------------------------------------------------------- section titles in other languages
# lower-case start of a section title -> (section type, epub:type, matter); English ones live in analyze.py
SECTION_KEYWORDS = {}
for _kind, _words in {
    ("toc", "toc", "front"): "inhalt|inhaltsverzeichnis|table des matières|sommaire|índice|sumário|indice|inhoud|"
        "innehåll|indhold|innhold|sisällys|spis treści|obsah|cuprins|tartalom|içindekiler|περιεχόμενα|содержание|"
        "оглавление|зміст|विषय-सूची|अनुक्रमणिका|ਤਤਕਰਾ|সূচিপত্র|பொருளடக்கம்|สารบัญ|目次|目录|目錄|차례|목차",
    ("chapter", "foreword", "front"): "vorwort|avant-propos|préface|prefacio|prefácio|prefazione|voorwoord|förord|"
        "forord|esipuhe|przedmowa|předmluva|prefață|előszó|önsöz|πρόλογος|предисловие|передмова|प्रस्तावना|भूमिका|"
        "ਭੂਮਿਕਾ|ভূমিকা|முன்னுரை|คำนำ|まえがき|序言|前言|머리말|서문",
    ("chapter", "introduction", "front"): "einleitung|einführung|introducción|introdução|introduzione|inleiding|"
        "inledning|indledning|innledning|johdanto|wstęp|úvod|introducere|bevezetés|giriş|εισαγωγή|введение|вступ|"
        "परिचय|ਜਾਣ-ਪਛਾਣ|সূচনা|அறிமுகம்|บทนำ|はじめに|引言|導言|들어가며",
    ("chapter", "epilogue", "body"): "nachwort|epílogo|epiloog|posłowie|doslov|epilogul|utószó|sonsöz|επίλογος|"
        "эпилог|епілог|उपसंहार|ਉਪਸੰਹਾਰ|উপসংহার|பின்னுரை|บทส่งท้าย|エピローグ|尾声|尾聲|에필로그",
    ("chapter", "afterword", "back"): "über die autorin|über den autor|à propos de l|sobre el autor|sobre la autora|"
        "sobre o autor|sobre a autora|l'autore|over de auteur|om författaren|om forfatteren|kirjailijasta|o autorze|"
        "o autorovi|despre autor|a szerzőről|yazar hakkında|σχετικά με τ|об авторе|про автора|लेखक के बारे में|"
        "ਲੇਖਕ ਬਾਰੇ|লেখক পরিচিতি|ஆசிரியர் பற்றி|เกี่ยวกับผู้เขียน|著者について|关于作者|關於作者|작가 소개|저자 소개",
    ("chapter", "acknowledgments", "back"): "danksagung|dank|remerciements|agradecimientos|agradecimentos|"
        "ringraziamenti|dankwoord|tack|tak|takk|kiitokset|podziękowania|poděkování|mulțumiri|köszönetnyilvánítás|"
        "teşekkür|ευχαριστίες|благодарности|подяки|आभार|ਧੰਨਵਾਦ|কৃতজ্ঞতা|நன்றி|กิตติกรรมประกาศ|謝辞|致谢|致謝|감사의 말",
    ("chapter", "dedication", "front"): "widmung|dédicace|dedicatoria|dedicatória|dedica|opdracht|tillägnan|"
        "dedikation|omistus|dedykacja|věnování|dedicație|ajánlás|ithaf|αφιέρωση|посвящение|присвята|समर्पण|"
        "ਸਮਰਪਣ|উৎসর্গ|சமர்ப்பணம்|คำอุทิศ|献辞|献词|獻詞|헌사",
    ("chapter", "glossary", "back"): "glossar|glossaire|glosario|glossário|glossario|woordenlijst|ordlista|ordliste|"
        "sanasto|słowniczek|slovníček|glosar|szójegyzék|sözlük|γλωσσάριο|глоссарий|словник|शब्दावली|ਸ਼ਬਦਾਵਲੀ|"
        "শব্দকোষ|சொற்களஞ்சியம்|อภิธานศัพท์|用語集|术语表|術語表|용어집",
}.items():
    for _w in _words.split("|"):
        SECTION_KEYWORDS[_w] = _kind
