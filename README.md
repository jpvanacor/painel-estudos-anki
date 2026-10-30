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
  - Na página da matéria: Renomear muda o nome do baralho (ele continua no mesmo lugar) e, no fim da página, Excluir o baralho apaga o baralho, os baralhos de dentro dele e os cartões, como no Anki. A exclusão pede confirmação e dá para desfazer logo em seguida.
  - Os baralhos de dentro da matéria (os dos tópicos da Roleta, por exemplo) aparecem numa lista própria, cada um com Estudar, Procurar, Renomear e Excluir.
- **Roleta**: a Roleta de Estudos dentro do painel, com as mesmas regras.
  - O sorteio não repete tópico até o ciclo acabar. Sortear outro devolve o tópico ao sorteio.
  - Subcategorias, anotações por tópico, histórico do ciclo, busca e desfazer.
  - Cada matéria da Roleta se liga a um baralho (pelo nome, ou escolhido em Organizar).
  - O tópico sorteado abre só os cartões dele: os artigos do nome do tópico ("Arts. 155 a 183") são comparados com o "[Art. 155, …]" do começo de cada cartão. Se o baralho tiver duas leis com o mesmo artigo, o tópico pergunta qual é a lei uma vez. Tópicos sem artigos podem ser ligados a uma etiqueta. A sessão usa um baralho filtrado temporário, desfeito ao encerrar, e as respostas contam como revisões normais.
  - A aba Tópicos mostra quantos cartões cada tópico tem no Anki.
  - Estudar, no tópico sorteado, cria o baralho do tópico dentro do baralho da matéria: Matéria::Subcategoria::Tópico (sem o nível do meio quando a matéria não tem subcategorias; uma subcategoria com "›" no nome, vinda de títulos aninhados, ganha um nível para cada parte). Os baralhos novos usam as mesmas opções do baralho da matéria, e o baralho do tópico fica como baralho atual do Anki, que é onde Adicionar cartões começa (a não ser que o Anki esteja configurado para escolher o baralho pelo tipo de nota). Os cartões que você já tinha ficam onde estão; os do baralho do tópico passam a contar como cartões do tópico. Se a matéria ainda não tiver baralho, o painel cria o dela também.
  - Importar: cole o bloco JSON da skill `exportar-roleta`, um tópico por linha, ou um backup da Roleta de Estudos. O backup traz os vistos, as datas e as anotações.
  - Backup: salve em arquivo ou copie. O arquivo também abre na Roleta de Estudos.
  - Atalho: Espaço gira.
- **Caderno de erros**: os cartões errados hoje, nos últimos 7 ou 30 dias, por matéria e por lei, com o gabarito, a correção e o verso. Refazer monta uma sessão só com eles (de todas as matérias ou de uma). Se você marcou os motivos dos erros, o caderno mostra qual aparece mais.
- **Celular (AnkiDroid)**: em Ajustes, Ativar no celular põe os botões C e E, e as letras das questões, dentro dos próprios cartões.
  - No AnkiDroid, tocar numa opção vira o cartão. O verso mostra se você acertou, risca a troca dos itens ERRADO e traz as notas do mesmo jeito do painel: errou, Continuar, que dá De novo; acertou, Difícil, Bom ou Fácil.
  - Feito para a tela de estudo padrão do AnkiDroid. Na tela de estudo nova, que ainda é experimental, o verso mostra o resultado e a nota fica nos botões do próprio AnkiDroid.
  - O código vai num bloco no fim da frente e do verso do modelo de cartão desses itens (em geral, o Básico). O resto do modelo não muda, Desativar tira o bloco, e a mudança vai para o celular numa sincronização normal, sem sincronização completa. No Anki do computador os cartões ficam iguais.
- **Sons e animações**: os sons são gerados pelo próprio painel, sem arquivos de áudio. Em Ajustes dá para desligar os sons, mudar o volume e desligar as animações. Se o Windows estiver com as animações desligadas (Acessibilidade, Efeitos visuais), as do painel também ficam.
- **Ajustes**: meta diária, onde estão as matérias, sons e animações. Tudo fica salvo dentro da coleção e sincroniza com ela.
- **Interface do Anki**: um botão devolve a janela ao Anki normal. Para voltar ao painel, use Ferramentas, Abrir o Painel de Estudos.

Quem usava o Edital da versão 0.1 não perde nada: ao abrir a 0.2 ou mais nova, cada matéria do Edital vira uma matéria da Roleta, com o que já tinha sido sorteado no ciclo.

## Instalar

1. Na pasta [`versoes`](versoes), abra o arquivo da versão mais nova (hoje, `painel_estudos-0.5.0.ankiaddon`) e baixe pelo botão de download do GitHub.
2. No Anki: Ferramentas, Extensões, Instalar de um arquivo. Escolha o arquivo e reinicie o Anki.

Para atualizar, instale o arquivo novo do mesmo jeito. Se algo der errado, segure Shift enquanto abre o Anki: ele abre sem extensões.

## Requisitos e limites

- Testado no Anki 26.09.3 (Python 3.13). O código roda em Python 3.9 ou mais novo, mas versões antigas do Anki não foram testadas.
- O painel é do computador: AnkiDroid e AnkiMobile não rodam extensões. No celular entram só os botões dentro dos cartões, e só no AnkiDroid: o código não age em outros aplicativos. A Roleta e o caderno de erros ficam salvos na coleção e vão junto na sincronização, mas só aparecem no computador.
- O conteúdo dos cartões aparece num quadro isolado: scripts do modelo de cartão não rodam, e cartões de digitar a resposta ou de oclusão de imagem devem ser estudados na interface normal do Anki.
- Baralhos filtrados não aparecem como matérias. Com um baralho de cima guardando as matérias, só os baralhos logo abaixo dele contam como matérias; os de mais baixo (como os dos tópicos) ficam dentro da matéria.

## Desenvolvimento

- `python3 -m pytest tests`: formatos de cartão, regras da Roleta e a ligação entre tópicos e cartões, sem precisar do Anki; `tests/test_decks.py` (quais baralhos são matérias) usa o pacote `anki` e é pulado onde ele não estiver instalado.
- `dev/run_gui_test.sh <pasta>`: abre um Anki de verdade numa tela virtual com um perfil de teste, clica por todas as telas (estudo, Roleta, importação de backup, cartões de um tópico, caderno de erros, baralho do tópico, renomear e excluir baralhos, tema escuro), tira capturas, mede os sons e mostra o que ficou gravado no histórico de revisões. Precisa de `pip install aqt` e `xvfb`.
- `python3 dev/celular_sim.py <pasta>`: renderiza cartões de teste com o bloco do celular, monta páginas no formato da tela de estudo do AnkiDroid e toca nas opções numa tela do tamanho de um celular, com capturas.
- `python3 build.py`: gera `dist/painel_estudos-<versão>.ankiaddon`. Cada versão publicada é copiada para `versoes/`.

Fontes: Barlow e Barlow Semi Condensed, licença SIL Open Font License (`painel_estudos/web/fonts/OFL-Barlow.txt`).
