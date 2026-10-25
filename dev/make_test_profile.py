"""Creates a throwaway Anki base folder for testing the add-on in a real Anki.

Cards follow the formats of the anki-lei-seca (Certo/Errado) and questoes-concurso (A to E)
skills, plus normal question/answer cards. Past answers are written to the review log so the
accuracy, weak spots and streak have something to show.

Usage: python3 dev/make_test_profile.py <base folder>
"""

import random
import sys
import time
from pathlib import Path

from aqt.profiles import ProfileManager, VideoDriver
from anki.collection import Collection

base = Path(sys.argv[1])
pm = ProfileManager(ProfileManager.get_created_base_folder(str(base)))
pm.setupMeta()
pm.setLang("pt_BR")
pm.create("Teste")
pm.set_video_driver(VideoDriver.Software)

profile = base / "Teste"
profile.mkdir(exist_ok=True)
col = Collection(str(profile / "collection.anki2"))
basic = col.models.by_name(col.tr.notetypes_basic_name()) or col.models.by_name("Basic")

CE = "<br><br>( ) Certo &nbsp;&nbsp;&nbsp; ( ) Errado"
PATRIMONIO = "direito_penal::CP::parte_especial::titulo_II::crimes_contra_patrimonio"
PESSOA = "direito_penal::CP::parte_especial::titulo_I::crimes_contra_pessoa"
IMPUTAB = "direito_penal::CP::parte_geral::titulo_III::imputabilidade_penal"

cards = {
    "Direito Penal": [
        (
            "[Art. 155, §1º] Se o furto é praticado durante o repouso noturno, a pena aumenta-se de metade." + CE,
            "<b>❌ ERRADO</b><br><br>🔁 metade → <b>1/3 (um terço)</b><br><br>O aumento pelo repouso noturno é de 1/3 (um terço), porque a vítima está mais vulnerável no horário em que as pessoas normalmente dormem.<br><br><i>📌 Exemplo: Pedro invade uma loja às 3h da manhã e leva mercadorias. A pena do furto simples sobe 1/3 (um terço).</i><br><br>📎 Art. 155, §1º, CP: <i>\"A pena aumenta-se de um terço, se o crime é praticado durante o repouso noturno.\"</i>",
            PATRIMONIO,
        ),
        (
            "[Art. 155, caput] Quem subtrai coisa alheia móvel para si ou para outrem comete furto simples, punido com reclusão de 01 (um) a 04 (quatro) anos e multa." + CE,
            "<b>✅ CERTO</b><br><br>É a regra do <b>furto simples</b>: pegar algo de outra pessoa sem violência nem ameaça. Com violência ou grave ameaça, deixa de ser furto e passa a ser roubo.<br><br><i>📌 Exemplo: Maria entra no vestiário da academia e pega o celular de outra pessoa da bolsa, escondido.</i><br><br>📎 Art. 155, caput, CP: <i>\"Subtrair, para si ou para outrem, coisa alheia móvel: Pena – reclusão, de 1 a 4 anos, e multa.\"</i>",
            PATRIMONIO,
        ),
        (
            "[Art. 155, §3º] Lucas liga uma extensão clandestina ao poste e passa a consumir energia elétrica sem pagar. Para o Código Penal, a energia elétrica não é coisa móvel e a conduta é atípica como furto." + CE,
            "<b>❌ ERRADO</b><br><br>🔁 não é coisa móvel → <b>equipara-se a coisa móvel</b><br><br>O Código Penal equipara à coisa móvel a energia elétrica e qualquer outra que tenha valor econômico, então o \"gato\" é furto.<br><br>📎 Art. 155, §3º, CP: <i>\"Equipara-se à coisa móvel a energia elétrica ou qualquer outra que tenha valor econômico.\"</i>",
            PATRIMONIO,
        ),
        (
            "[Art. 121, caput] A pena do homicídio simples é de reclusão de 06 (seis) a 20 (vinte) anos." + CE,
            "<b>✅ CERTO</b><br><br>O homicídio simples tem pena de <b>reclusão de 06 (seis) a 20 (vinte) anos</b>.<br><br>📎 Art. 121, caput, CP: <i>\"Matar alguém: Pena – reclusão, de seis a vinte anos.\"</i>",
            PESSOA,
        ),
        (
            "[Art. 121, §2º, I] O homicídio praticado por motivo torpe é qualificado." + CE,
            "<b>✅ CERTO</b><br><br>O motivo torpe (vil, repugnante) está entre as qualificadoras do homicídio.<br><br>📎 Art. 121, §2º, I, CP: <i>\"mediante paga ou promessa de recompensa, ou por outro motivo torpe\"</i>",
            PESSOA,
        ),
        (
            "[Art. 28, II] Se Pedro bebe voluntariamente até ficar embriagado e, nesse estado, agride Lucas, sua culpabilidade fica excluída." + CE,
            "<b>❌ ERRADO</b><br><br>🔁 fica excluída → <b>não exclui a imputabilidade</b><br><br>A embriaguez voluntária ou culposa não exclui a imputabilidade penal: Pedro responde pela agressão.<br><br>📎 Art. 28, II, CP: <i>\"Não excluem a imputabilidade penal: (...) II – a embriaguez, voluntária ou culposa, pelo álcool ou substância de efeitos análogos.\"</i>",
            IMPUTAB,
        ),
    ],
    "Processo Penal": [
        (
            "[Art. 46] Estando o réu preso, o MP tem 15 (quinze) dias para oferecer a denúncia." + CE,
            "<b>❌ ERRADO</b><br><br>🔁 15 (quinze) dias → <b>05 (cinco) dias</b><br><br>Com o réu preso, o prazo é de 05 (cinco) dias; com o réu solto, de 15 (quinze) dias.<br><br>📎 Art. 46, CPP: <i>\"O prazo para oferecimento da denúncia, estando o réu preso, será de 5 dias (...) e de 15 dias, se o réu estiver solto ou afiançado.\"</i>",
            "processo_penal::CPP::acao_penal",
        ),
    ],
    "Direito Administrativo": [
        (
            "<b>Direito Administrativo — Improbidade Administrativa</b><br>FUNDATEC — 2026 — Prefeitura de Pontão/RS — Técnico de Enfermagem<br><br>Giba, servidor público do Município de Pontão/RS, revelou propositalmente um fato de que teve ciência em razão das suas atribuições e que deveria permanecer em segredo, propiciando beneficiamento por informação privilegiada e colocando em risco a segurança da sociedade e do Estado. É correto afirmar que ele cometeu um ato de improbidade administrativa<br><br>A) decorrente de concessão ou aplicação indevida de benefício financeiro ou tributário.<br>B) que atenta contra os princípios da administração pública.<br>C) que causa prejuízo ao erário.<br>D) que importa enriquecimento ilícito.",
            "<b>Gabarito: B</b><br><br>A conduta de Giba, revelar <b>propositalmente</b> fato sigiloso de que teve ciência em razão das atribuições, configura ato de improbidade que <b>atenta contra os princípios da administração pública</b> (art. 11, Lei 8.429/92).<br><br><b>Por que as outras estão erradas:</b><br><br><b>A)</b> A concessão indevida de benefício financeiro ou tributário trata de renúncia de receita. Nada a ver com revelação de segredo.<br><br><b>C)</b> Prejuízo ao erário (art. 10) exige <b>perda patrimonial efetiva</b>.<br><br><b>D)</b> Enriquecimento ilícito (art. 9) exige que o agente obtenha <b>vantagem patrimonial indevida</b>.<br><br>📎 Art. 11, VII, Lei 8.429/92: <i>\"revelar fato ou circunstância de que tem ciência em razão das atribuições e que deva permanecer em segredo\"</i>",
            "direito_administrativo::lei_8429::atos_de_improbidade::contra_principios banca::fundatec ano::2026",
        ),
        (
            "<b>Direito Administrativo — Licitações</b><br>Questão de treino<br><br>Segundo a Lei 14.133/2021, são modalidades de licitação:<br><br>A) pregão, concorrência, concurso, leilão e diálogo competitivo.<br>B) concorrência, tomada de preços, convite, concurso e leilão.<br>C) pregão, convite, concurso, leilão e diálogo competitivo.<br>D) concorrência, tomada de preços, pregão e leilão.<br>E) pregão, concorrência, concurso e credenciamento.",
            "<b>Gabarito: A</b><br><br>O art. 28 da Lei 14.133/2021 lista cinco modalidades: <b>pregão, concorrência, concurso, leilão e diálogo competitivo</b>.<br><br><b>Por que as outras estão erradas:</b><br><br><b>B)</b> Tomada de preços e convite eram modalidades da Lei 8.666/93 e não existem na lei nova.<br><br><b>C)</b> O convite não existe na Lei 14.133/2021.<br><br><b>D)</b> A tomada de preços não existe na Lei 14.133/2021.<br><br><b>E)</b> O credenciamento é procedimento auxiliar (art. 78), não modalidade.<br><br>📎 Art. 28, Lei 14.133/2021: <i>\"São modalidades de licitação: I – pregão; II – concorrência; III – concurso; IV – leilão; V – diálogo competitivo.\"</i>",
            "direito_administrativo::lei_14133::modalidades",
        ),
    ],
    "Direito Civil": [
        ("Qual é o prazo prescricional geral no Código Civil?", "10 anos (art. 205 do CC)", "direito_civil::CC::prescricao"),
        ("Qual é o prazo da pretensão de reparação civil?", "3 anos (art. 206, § 3º, V, do CC)", "direito_civil::CC::prescricao"),
    ],
}

notes_by_deck = {}
for deck, items in cards.items():
    did = col.decks.id(deck)
    notes_by_deck[deck] = []
    for front, back, tags in items:
        note = col.new_note(basic)
        note.fields[0], note.fields[1] = front, back
        note.tags = tags.split()
        col.add_note(note, did)
        notes_by_deck[deck].append(note)

# Some cards become reviews due today, the rest stay new.
review_cids = []
for deck, take in (("Direito Penal", [1, 3, 4]), ("Direito Administrativo", [1])):
    for i in take:
        review_cids.append(notes_by_deck[deck][i].cards()[0].id)
col.sched.set_due_date(review_cids, "0")

# Past answers: accuracy differs per tag, so the weak spots and the order of the plan show up.
rng = random.Random(4)
accuracy_by_tag = {PATRIMONIO: 0.52, PESSOA: 0.86, IMPUTAB: 0.6}
day_start = col.sched.day_cutoff - 86400
rows = []
rid = (day_start - 30 * 86400) * 1000
for day in range(-21, 1):
    per_deck = {"Direito Penal": 34, "Processo Penal": 6, "Direito Administrativo": 18, "Direito Civil": 12}
    if day == 0:
        per_deck = {"Direito Penal": 18, "Processo Penal": 3, "Direito Administrativo": 9, "Direito Civil": 7}
    for deck, n in per_deck.items():
        for _ in range(n):
            note = rng.choice(notes_by_deck[deck])
            cid = note.cards()[0].id
            tag = note.tags[0]
            p = accuracy_by_tag.get(tag, {"Processo Penal": 0.78, "Direito Administrativo": 0.7, "Direito Civil": 0.9}.get(deck, 0.8))
            ease = 3 if rng.random() < p else 1
            if day == 0:
                when = int(time.time()) - rng.randint(60, 3 * 3600)
                when = max(when, day_start + 60)
            else:
                when = day_start + day * 86400 + rng.randint(8 * 3600, 22 * 3600)
            rid = max(rid + 1, when * 1000 + rng.randint(0, 999))
            rows.append((rid, cid, -1, ease, 5, 2, 2501, rng.randint(6000, 14000), 1))  # factor 2501 marks fake history
col.db.executemany("insert into revlog (id, cid, usn, ease, ivl, lastIvl, factor, time, type) values (?,?,?,?,?,?,?,?,?)", rows)

# Settings as Painel 0.1 left them: an edital in the old shape, converted to the Roleta on the
# first run. The goal sits just above today's answers, so the session crosses it.
yesterday = int(time.time()) - 86400
col.set_config(
    "painelEstudos",
    {
        "version": 1,
        "goal": {"unit": "cards", "value": 39},
        "edital": {
            "cycle": 1,
            "current": "e2",
            "materias": [
                {
                    "name": "Direito Civil",
                    "deck": None,
                    "groups": [
                        {
                            "name": None,
                            "topics": [
                                {"id": "e1", "name": "Prescrição e decadência (Arts. 189 a 211)", "drawn": 1, "done": 1, "times": 1, "last": yesterday},
                                {"id": "e2", "name": "Negócio jurídico (Arts. 104 a 184)", "drawn": 1, "done": 0, "times": 1, "last": None},
                                {"id": "e3", "name": "Pessoas naturais (Arts. 1º a 39)", "drawn": 0, "done": 0, "times": 0, "last": None},
                            ],
                        }
                    ],
                }
            ],
        },
    },
)
col.close()
print(f"profile ready: {len(rows)} past answers, base {base}")
