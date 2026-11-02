"""Language support: detection, multilingual layout keywords, line joining for
scripts without spaces, text-layer repair and checks, EPUB labels.

All sample sentences are invented filler."""
from aldleaf.i18n import (BYLINE_CAPTURE, CHAPTER_LABEL, WARN_HDR, detect_language, joins_without_space,
                          labels, page_label, repair_text_layer, text_layer_issues, unsupported_layout)
from aldleaf.text import Dehyphenator, append_line, runs_text


class _NoLangDoc:
    def pdf_catalog(self):
        raise RuntimeError


SAMPLES = {
    "en": "The morning arrived quietly over the harbour and nobody remembered the lantern. She remembered it only when the harbour had gone dark.",
    "de": "Der Morgen kam leise über den Hafen, und niemand dachte an die Laterne. Sie erinnerte sich an die Laterne erst, als der Hafen dunkel war.",
    "fr": "Le matin est arrivé doucement sur le port et personne ne pensait à la lanterne. Elle se souvenait de la lanterne seulement quand le port était dans le noir.",
    "es": "La mañana llegó despacio sobre el puerto y nadie se acordó de la linterna. Ella pensó en la linterna solo cuando el puerto estaba oscuro.",
    "pt": "A manhã chegou devagar sobre o porto e ninguém se lembrou da lanterna. Ela pensou na lanterna só quando o porto estava escuro.",
    "it": "La mattina arrivò piano sul porto e nessuno si ricordò della lanterna. Lei pensò alla lanterna solo quando il porto era del tutto buio.",
    "nl": "De ochtend kwam stil over de haven en niemand dacht aan de lantaarn. Zij dacht pas aan de lantaarn toen de haven helemaal donker was.",
    "sv": "Morgonen kom tyst över hamnen och ingen tänkte på lyktan. Hon kom att tänka på lyktan först när hamnen var helt mörk.",
    "da": "Morgenen kom stille over havnen, og ingen tænkte på lygten. Hun kom først i tanke om lygten, da havnen var helt mørk, og hun havde ikke noget lys.",
    "nb": "Morgenen kom stille over havnen, og ingen tenkte på lykten. Hun kom ikke på lykten før havnen var helt mørk, og hun hadde ikke noe lys.",
    "pl": "Ranek przyszedł cicho nad port i nikt nie pomyślał o latarni. Przypomniała sobie o latarni dopiero wtedy, gdy port był zupełnie ciemny.",
    "ru": "Утро пришло тихо над гаванью, и никто не вспомнил о фонаре. Она вспомнила о фонаре только тогда, когда гавань стала совсем тёмной.",
    "uk": "Ранок прийшов тихо над гаванню, і ніхто не згадав про ліхтар. Вона згадала про ліхтар лише тоді, коли гавань стала зовсім темною.",
    "el": "Το πρωί ήρθε ήσυχα πάνω από το λιμάνι και κανείς δεν σκέφτηκε το φανάρι.",
    "hi": "सुबह चुपचाप बंदरगाह पर आई और किसी ने लालटेन के बारे में नहीं सोचा। उसे लालटेन की याद तभी आई जब बंदरगाह पूरी तरह अँधेरा हो चुका था।",
    "pa": "ਸਵੇਰ ਚੁੱਪਚਾਪ ਬੰਦਰਗਾਹ ਉੱਤੇ ਆਈ ਅਤੇ ਕਿਸੇ ਨੇ ਲਾਲਟੈਣ ਬਾਰੇ ਨਹੀਂ ਸੋਚਿਆ।",
    "bn": "সকাল নিঃশব্দে বন্দরে এল আর কেউ লণ্ঠনের কথা ভাবল না।",
    "ta": "காலை அமைதியாக துறைமுகத்தின் மேல் வந்தது, யாரும் விளக்கைப் பற்றி நினைக்கவில்லை.",
    "th": "เช้ามาถึงท่าเรืออย่างเงียบงันและไม่มีใครนึกถึงตะเกียง",
    "ja": "朝は静かに港へやって来て、誰もランタンのことを思い出さなかった。",
    "zh-Hans": "早晨安静地来到港口，没有人想起那盏灯。这时已经太晚了，她说这本书没有人读。",
    "zh-Hant": "早晨安靜地來到港口，沒有人想起那盞燈。這時已經太晚了，她說這本書沒有人讀。",
    "ko": "아침이 조용히 항구 위로 찾아왔고 아무도 등불을 떠올리지 않았다.",
}


def test_detects_book_language_across_scripts():
    for lang, text in SAMPLES.items():
        assert detect_language(_NoLangDoc(), text * 4) == (lang, "text"), lang
    assert detect_language(_NoLangDoc(), "Short.") == ("en", "default")


def test_multilingual_layout_keywords():
    assert BYLINE_CAPTURE.match("Von: Ada Beispiel").group(1) == "Ada Beispiel"
    assert BYLINE_CAPTURE.match("作者：样本 花").group(1) == "样本 花"
    assert BYLINE_CAPTURE.match("लेखक: अदा उदाहरण").group(1) == "अदा उदाहरण"
    for label in ("Chapter 1", "Kapitel 3", "Capítulo IV", "1. fejezet", "Глава 2", "अध्याय १", "บทที่ 5",
                  "第1章", "第一章", "제1장", "Luku 2"):
        assert CHAPTER_LABEL.match(label), label
    for head in ("Trigger Warnings:", "Inhaltswarnungen:", "İçerik uyarıları:", "Προειδοποιήσεις:", "内容警告"):
        assert WARN_HDR.match(head), head


def test_lines_join_without_spaces_only_where_the_script_has_none():
    assert joins_without_space("港", "へ") and joins_without_space("ง", "เ")
    assert not joins_without_space("a", "b") and not joins_without_space("다", "그")
    dh = Dehyphenator(False)
    runs = [("灯台守は毎晩階段を", frozenset())]
    append_line(runs, [("数えた。", frozenset())], dh)
    assert runs_text(runs) == "灯台守は毎晩階段を数えた。"
    runs = [("ทุกเย็น ", frozenset())]           # Thai phrase ends in a real space: keep it
    append_line(runs, [("แม้ว่า", frozenset())], dh)
    assert runs_text(runs) == "ทุกเย็น แม้ว่า"
    runs = [("놋쇠는 가장자리", frozenset())]     # Korean line broke before a particle
    append_line(runs, [("부터 초록색으로", frozenset())], dh)
    assert runs_text(runs) == "놋쇠는 가장자리부터 초록색으로"


def test_text_layer_repair_and_damage_check():
    assert repair_text_layer("अध्याायय") == "अध्यायय"           # doubled vowel sign
    assert repair_text_layer("रेलिंंग") == "रेलिंग"              # doubled anusvara
    assert text_layer_issues("हिन्दी पुस्तक")[0] == 0
    assert text_layer_issues("हȭ øदी पु�तक")[0] >= 2          # stray symbols and unreadable glyphs


def test_unsupported_layouts_are_refused_with_a_reason():
    assert "right-to-left" in unsupported_layout("كان حارس المنارة يعد الدرجات كل مساء " * 5, 0, 100)
    assert "vertical" in unsupported_layout("縦書き", 80, 100)
    assert unsupported_layout("An ordinary English book.", 0, 100) is None


def test_labels_follow_language_with_english_fallback():
    assert labels("de-DE")["contents"] == "Inhalt"
    assert labels("fr")["by"] == "Par"
    assert labels("zh-TW")["contents"] == "目錄" and labels("zh-CN")["contents"] == "目录"
    assert labels("no")["contents"] == "Innhold"
    assert labels("xx")["contents"] == "Contents"
    assert page_label(labels("ja"), 5) == "5ページ" and page_label(labels("de"), 5) == "Seite 5"


def test_ambiguous_byline_words_need_a_name():
    from aldleaf.i18n import BYLINE
    assert BYLINE.match("By Ada Example") and BYLINE.match("Door Ada Voorbeeld") and BYLINE.match("Von: Ada")
    assert not BYLINE.match("By the Sea") and not BYLINE.match("De signalen") and not BYLINE.match("von den Bergen")


def test_korean_breaks_follow_the_books_vocabulary_and_grammar():
    from aldleaf.text import _split_hangul
    dh = Dehyphenator(False)
    for line in ("그 수는 한 번도 바뀌지 않았다 다시", "아이 등대지기는 매일 저녁 계단을 세었지만 그"):
        dh.learn(line)
    assert _split_hangul("한 번도 바", "뀌지 않았다", dh)        # neither half is a word: one word
    assert _split_hangul("날씨를 적", "었다.", dh)               # tense syllable can't start a word
    assert not _split_hangul("한 번도", "바뀌지 않았다", dh)      # a known word on the next line
    assert not _split_hangul("수는 한 번도", "바꿈 없이", dh)     # ends on a closing particle


def test_list_numbers_stored_in_pieces_are_removed():
    from aldleaf.render import _strip_bullet
    runs = [("1", frozenset()), (". ", frozenset()), ("아침이 왔다.", frozenset())]
    assert "".join(t for t, _ in _strip_bullet(runs, "1.")) == "아침이 왔다."
