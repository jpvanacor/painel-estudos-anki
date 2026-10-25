# Painel de Estudos

Extensão do Anki que troca a janela principal por uma interface de estudo para concurso. O Anki continua guardando os cartões, calculando os intervalos, sincronizando e abrindo as próprias janelas (Adicionar, Procurar, Estatísticas, Opções do baralho). O painel só desenha as telas e pede os dados ao Anki.

## O que tem

- **Hoje**: meta diária (cartões ou minutos) em bolinhas de gabarito, sequência de dias batendo a meta, as matérias de hoje da mais fraca para a mais forte e o último tópico sorteado na Roleta.
- **Estudo**:
  - Cartões Certo/Errado (formato da skill `anki-lei-seca`) ganham os botões C e E.
  - Questões (formato da skill `questoes-concurso`) ganham alternativas clicáveis de A a E.
  - Errou: o cartão vai direto para De novo, e dá para marcar o motivo (Não sabia, Confundi, Falta de atenção ou Pegadinha). Acertou: você escolhe Difícil, Bom ou Fácil.
  - Nos itens ERRADO, depois de responder, o enunciado mostra riscadas as palavras trocadas e, ao lado, o que a lei diz (pela linha 🔁 do verso).
  - Qualquer outro cartão funciona como no Anki: Mostrar resposta e os quatro botões.
  - Teclas: C/E, A a E, Espaço, 1 a 4, Ctrl+Z para desfazer, Esc para encerrar. Depois de errar: N, C, A ou P para o motivo.
- **Matérias**: cada baralho é uma matéria, com acerto em 30 dias, estágio dos cartões, os temas mais fracos pelas etiquetas e o andamento da Roleta.
- **Roleta**: a Roleta de Estudos dentro do painel, com as mesmas regras.
  - O sorteio não repete tópico até o ciclo acabar. Sortear outro devolve o tópico ao sorteio.
  - Subcategorias, anotações por tópico, histórico do ciclo, busca e desfazer.
  - Cada matéria da Roleta se liga a um baralho (pelo nome, ou escolhido em Organizar).
  - O tópico sorteado abre só os cartões dele: os artigos do nome do tópico ("Arts. 155 a 183") são comparados com o "[Art. 155, …]" do começo de cada cartão. Se o baralho tiver duas leis com o mesmo artigo, o tópico pergunta qual é a lei uma vez. Tópicos sem artigos podem ser ligados a uma etiqueta. A sessão usa um baralho filtrado temporário, desfeito ao encerrar, e as respostas contam como revisões normais.
  - A aba Tópicos mostra quantos cartões cada tópico tem no Anki.
  - Importar: cole o bloco JSON da skill `exportar-roleta`, um tópico por linha, ou um backup da Roleta de Estudos. O backup traz os vistos, as datas e as anotações.
  - Backup: salve em arquivo ou copie. O arquivo também abre na Roleta de Estudos.
  - Atalho: Espaço gira.
- **Caderno de erros**: os cartões errados hoje, nos últimos 7 ou 30 dias, por matéria e por lei, com o gabarito, a correção e o verso. Refazer monta uma sessão só com eles (de todas as matérias ou de uma). Se você marcou os motivos dos erros, o caderno mostra qual aparece mais.
- **Sons e animações**: os sons são gerados pelo próprio painel, sem arquivos de áudio. Em Ajustes dá para desligar os sons, mudar o volume e desligar as animações. Se o Windows estiver com as animações desligadas (Acessibilidade, Efeitos visuais), as do painel também ficam.
- **Ajustes**: meta diária, onde estão as matérias, sons e animações. Tudo fica salvo dentro da coleção e sincroniza com ela.
- **Interface do Anki**: um botão devolve a janela ao Anki normal. Para voltar ao painel, use Ferramentas, Abrir o Painel de Estudos.

Quem usava o Edital da versão 0.1 não perde nada: ao abrir a 0.2 ou mais nova, cada matéria do Edital vira uma matéria da Roleta, com o que já tinha sido sorteado no ciclo.

## Instalar

1. Na pasta [`versoes`](versoes), abra o arquivo da versão mais nova (hoje, `painel_estudos-0.3.0.ankiaddon`) e baixe pelo botão de download do GitHub.
2. No Anki: Ferramentas, Extensões, Instalar de um arquivo. Escolha o arquivo e reinicie o Anki.

Para atualizar, instale o arquivo novo do mesmo jeito. Se algo der errado, segure Shift enquanto abre o Anki: ele abre sem extensões.

## Requisitos e limites

- Testado no Anki 26.09.3 (Python 3.13). O código roda em Python 3.9 ou mais novo, mas versões antigas do Anki não foram testadas.
- Só no computador. AnkiDroid e AnkiMobile não rodam extensões; no celular o Anki continua com a interface normal, e as revisões se encontram pela sincronização. A Roleta fica salva na coleção, então vai junto na sincronização, mas só aparece no computador.
- O conteúdo dos cartões aparece num quadro isolado: scripts do modelo de cartão não rodam, e cartões de digitar a resposta ou de oclusão de imagem devem ser estudados na interface normal do Anki.
- Baralhos filtrados não aparecem como matérias.

## Desenvolvimento

- `python3 -m pytest tests`: formatos de cartão, regras da Roleta e a ligação entre tópicos e cartões, sem precisar do Anki.
- `dev/run_gui_test.sh <pasta>`: abre um Anki de verdade numa tela virtual com um perfil de teste, clica por todas as telas (estudo, Roleta, importação de backup, cartões de um tópico, caderno de erros, tema escuro), tira capturas, mede os sons e mostra o que ficou gravado no histórico de revisões. Precisa de `pip install aqt` e `xvfb`.
- `python3 build.py`: gera `dist/painel_estudos-<versão>.ankiaddon`. Cada versão publicada é copiada para `versoes/`.

Fontes: Barlow e Barlow Semi Condensed, licença SIL Open Font License (`painel_estudos/web/fonts/OFL-Barlow.txt`).
