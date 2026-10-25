"""Finding a Roleta topic's cards: articles in topic names and on card fronts, laws from tags."""

import importlib.util
import sys
from pathlib import Path

import pytest

# Loaded by path: importing the package would start the add-on, which needs a running Anki.
_spec = importlib.util.spec_from_file_location("topics", Path(__file__).parents[1] / "painel_estudos" / "topics.py")
topics = importlib.util.module_from_spec(_spec)
sys.modules["topics"] = topics
_spec.loader.exec_module(topics)


@pytest.mark.parametrize(
    "name, expected",
    [
        # topic names as the exportar-roleta skill writes them
        ("Princípios fundamentais (Arts. 1º a 4º)", [(1, 4)]),
        ("Direitos e deveres individuais e coletivos (Art. 5º)", [(5, 5)]),
        ("Direitos sociais (Arts. 6º a 11)", [(6, 11)]),
        ("Organização político-administrativa (Arts. 18 e 19)", [(18, 18), (19, 19)]),
        ("Administração pública – disposições gerais (Arts. 37 e 38)", [(37, 37), (38, 38)]),
        ("Crimes contra o patrimônio (Arts. 155 a 183)", [(155, 183)]),
        ("Propriedade (Arts. 1.228 a 1.368)", [(1228, 1368)]),
        ("Crimes contra a pessoa (Arts. 121 a 154-B)", [(121, 154)]),
        ("Vários (Arts. 5º a 17 e 22)", [(5, 17), (22, 22)]),
        ("Habeas corpus (Art. 5º, LXVIII)", [(5, 5)]),
        ("Licitação (arts. 100-110)", [(100, 110)]),
        ("Disposições (artigos 1º ao 3º)", [(1, 3)]),
        # no articles
        ("Modalidades", []),
        ("Lei 8.429/1992 – Sanções", []),
        ("Partes do processo", []),
    ],
)
def test_topic_articles(name, expected):
    assert topics.parse_articles(name) == expected


@pytest.mark.parametrize(
    "front, expected",
    [
        ("[Art. 155, §1º] Se o furto é praticado durante o repouso noturno.<br><br>( ) Certo &nbsp;&nbsp;&nbsp; ( ) Errado", [(155, 155)]),
        ("[Art. 121, §2º, I] O homicídio praticado por motivo torpe é qualificado.", [(121, 121)]),
        ("<div>[Art. 1.228, caput] O proprietário tem a faculdade de usar.</div>", [(1228, 1228)]),
        ("[Arts. 155 e 157] Furto e roubo.", [(155, 155), (157, 157)]),
        ("[Súmula 711, STF] A lei penal mais grave aplica-se ao crime continuado.", []),
        ("Segundo o art. 155 do CP, é furto...", []),  # only the leading reference counts
    ],
)
def test_card_articles(front, expected):
    assert topics.card_articles(front) == expected


def test_ranges_label():
    assert topics.ranges_label([(155, 183)]) == "pelos arts. 155 a 183"
    assert topics.ranges_label([(5, 5)]) == "pelo art. 5"
    assert topics.ranges_label([(18, 18), (19, 19)]) == "pelos arts. 18 e 19"
    assert topics.ranges_label([(5, 17), (22, 22), (30, 30)]) == "pelos arts. 5 a 17, 22 e 30"


def test_law_of_tags():
    assert topics.law_of_tags("direito_penal::CP::parte_especial::titulo_II::crimes_contra_patrimonio") == ("cp", "CP")
    assert topics.law_of_tags("banca::fundatec direito_administrativo::lei_8429::sancoes ano::2026") == ("lei8429", "Lei 8429")
    assert topics.law_of_tags("leech marked") is None
    assert topics.tag_label("direito_penal::CP::parte_especial::crimes_contra_patrimonio") == "CP › Parte especial › Crimes contra patrimonio"


def test_statement_drops_the_options_line():
    front = "[Art. 46] Estando o réu preso, o MP tem 15 (quinze) dias para oferecer a denúncia.<br><br>( ) Certo &nbsp;&nbsp;&nbsp; ( ) Errado"
    assert topics.statement(front) == "[Art. 46] Estando o réu preso, o MP tem 15 (quinze) dias para oferecer a denúncia."


def entry(cid, front, tags, ok=True):
    law = topics.law_of_tags(tags)
    return {
        "cid": cid,
        "ok": ok,
        "arts": topics.card_articles(front),
        "law": law[0] if law else None,
        "law_label": law[1] if law else None,
        "tags": topics.content_tags(tags),
    }


CP = "direito_penal::CP::parte_especial::titulo_II::crimes_contra_patrimonio"
DROGAS = "direito_penal::lei_11343::crimes"
DECK = [
    entry(1, "[Art. 155, caput] Furto simples.", CP),
    entry(2, "[Art. 155, §1º] Repouso noturno.", CP),
    entry(3, "[Art. 157] Roubo.", CP),
    entry(4, "[Art. 157, §2º] Roubo majorado.", CP, ok=False),  # suspended
    entry(5, "[Art. 121] Homicídio.", "direito_penal::CP::parte_especial::titulo_I::crimes_contra_pessoa"),
    entry(6, "[Art. 33, §2º] Regime fechado.", "direito_penal::CP::parte_geral::penas"),
    entry(7, "[Art. 33, caput] Tráfico de drogas.", DROGAS),
    entry(8, "[Art. 35] Associação para o tráfico.", DROGAS),
    entry(9, "Qual é a pena do furto?", CP),
]


def test_topic_cards_by_articles():
    info = topics.topic_cards("Crimes contra o patrimônio (Arts. 155 a 183)", None, DECK, ["Parte especial", "Direito Penal"])
    assert info["mode"] == "articles"
    assert info["cids"] == [1, 2, 3]  # the suspended card and the card without "[Art." are left out
    assert info["law"] == "cp" and not info["ambiguous"]
    assert info["arts_label"] == "pelos arts. 155 a 183"


def test_two_laws_with_the_same_article_need_a_choice():
    info = topics.topic_cards("Penas (Arts. 32 a 52)", None, DECK, ["Parte geral", "Direito Penal"])
    assert info["ambiguous"] and info["cids"] == []
    assert {law["key"] for law in info["laws"]} == {"cp", "lei11343"}
    chosen = topics.topic_cards("Penas (Arts. 32 a 52)", {"law": "cp"}, DECK, ["Parte geral", "Direito Penal"])
    assert chosen["cids"] == [6] and chosen["chosen"] and not chosen["ambiguous"]


def test_the_subcategory_name_picks_the_law():
    info = topics.topic_cards("Crimes (Arts. 33 a 47)", None, DECK, ["Lei 11.343/2006", "Legislação Penal Especial"])
    assert info["law"] == "lei11343" and info["cids"] == [7, 8]
    by_code = topics.topic_cards("Penas (Arts. 32 a 52)", None, DECK, ["Parte geral", "Código Penal"])
    assert by_code["law"] == "cp" and by_code["cids"] == [6]


def test_topic_cards_by_tag():
    info = topics.topic_cards("Furto e roubo", {"tag": "direito_penal::CP::parte_especial::titulo_II"}, DECK, ["Direito Penal"])
    assert info["mode"] == "tag" and info["cids"] == [1, 2, 3, 9]
    assert not info["has_articles"]


def test_topic_without_articles_or_tag():
    info = topics.topic_cards("Modalidades", None, DECK, ["Direito Administrativo"])
    assert info["mode"] == "none" and info["cids"] == []


def test_suggest_tag():
    counts = topics.tag_counts(DECK)
    assert counts["direito_penal::CP"] == 6
    assert topics.suggest_tag("Crimes contra o patrimônio", counts) == CP
    assert topics.suggest_tag("Crimes contra a pessoa", counts) == "direito_penal::CP::parte_especial::titulo_I::crimes_contra_pessoa"
    assert topics.suggest_tag("Recursos", counts) is None
