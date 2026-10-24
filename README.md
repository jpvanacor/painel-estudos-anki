# Painel de Estudos

Extensão do Anki que troca a janela principal por uma interface de estudo para concurso. O Anki continua guardando os cartões, calculando os intervalos, sincronizando e abrindo as próprias janelas (Adicionar, Procurar, Estatísticas, Opções do baralho). O painel só desenha as telas e pede os dados ao Anki.

## O que tem

- **Hoje**: meta diária (cartões ou minutos) em bolinhas de gabarito, sequência de dias batendo a meta, as matérias de hoje da mais fraca para a mais forte e o tópico do edital sorteado.
- **Estudo**:
  - Cartões Certo/Errado (formato da skill `anki-lei-seca`) ganham os botões C e E.
  - Questões (formato da skill `questoes-concurso`) ganham alternativas clicáveis de A a E.
  - Errou: o cartão vai direto para De novo. Acertou: você escolhe Difícil, Bom ou Fácil.
  - Qualquer outro cartão funciona como no Anki: Mostrar resposta e os quatro botões.
  - Teclas: C/E, A a E, Espaço, 1 a 4, Ctrl+Z para desfazer, Esc para encerrar.
- **Matérias**: cada baralho é uma matéria, com acerto em 30 dias, estágio dos cartões e os temas mais fracos pelas etiquetas.
- **Edital**: cole o mesmo bloco JSON da Roleta de Estudos. O sorteio não repete tópico até o ciclo acabar.
- **Ajustes**: meta diária e onde estão as matérias. Tudo fica salvo dentro da coleção e sincroniza com ela.
- **Interface do Anki**: um botão devolve a janela ao Anki normal. Para voltar ao painel, use Ferramentas, Abrir o Painel de Estudos.

## Instalar

1. Baixe o arquivo `.ankiaddon` da última versão em *Releases*.
2. No Anki: Ferramentas, Extensões, Instalar de um arquivo. Escolha o arquivo e reinicie o Anki.

Se algo der errado, segure Shift enquanto abre o Anki: ele abre sem extensões.

## Requisitos e limites

- Testado no Anki 26.09.3 (Python 3.13). O código roda em Python 3.9 ou mais novo, mas versões antigas do Anki não foram testadas.
- Só no computador. AnkiDroid e AnkiMobile não rodam extensões; no celular o Anki continua com a interface normal, e as revisões se encontram pela sincronização.
- O conteúdo dos cartões aparece num quadro isolado: scripts do modelo de cartão não rodam, e cartões de digitar a resposta ou de oclusão de imagem devem ser estudados na interface normal do Anki.
- Baralhos filtrados não aparecem como matérias.

## Desenvolvimento

- `python3 -m pytest tests`: formatos de cartão e edital, sem precisar do Anki.
- `dev/run_gui_test.sh <pasta>`: abre um Anki de verdade numa tela virtual com um perfil de teste, clica por todas as telas, tira capturas e mostra o que ficou gravado no histórico de revisões. Precisa de `pip install aqt` e `xvfb`.
- `python3 build.py`: gera `dist/painel_estudos-<versão>.ankiaddon`.

Fontes: Barlow e Barlow Semi Condensed, licença SIL Open Font License (`painel_estudos/web/fonts/OFL-Barlow.txt`).
