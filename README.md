# Divã do Vão

Ferramenta de co-produção musical e ciclo de canções a partir de Rumi, com
**ritmo derivado do aruz persa**, **colorido Clube da Esquina** e
**auditabilidade** de ponta a ponta.

> A rítmica da melodia não é inventada: ela deriva das sílabas longas e curtas
> do persa original de Rumi. Cada nota rastreia até a sílaba que a originou.

## Início rápido

```bash
# 1. app local (só Python 3.10+, sem dependências)
python3 app/server.py
# abra http://localhost:8000

# 2. testes de auditabilidade
python3 tests/test_auditabilidade.py      # esperado: 54/54

# 3. gerar uma melodia por linha de comando
python3 engine/generative.py --verso masnavi_1 --modo dorico

# 4. medir: quanto desta canção é Rumi, quanto é o sorteio
python3 engine/generative.py --verso masnavi_1 --complexidade \
        --letra "Es-cu-ta o jun-co con-tan-do a dor"

# 5. exportar partitura e MIDI (com o relatório de auditoria ao lado)
python3 engine/generative.py --verso masnavi_1 --export musicxml,midi

# 6. o pipeline inteiro: gerar muitas, peneirar, medir e escolher um lote
python3 engine/pipeline.py --verso masnavi_1 --n 300 --lote 8

# 7. ensinar o gosto (~40 comparações bastam; depois o ganho estaciona)
python3 engine/pipeline.py --verso masnavi_1 --julgar 40
python3 engine/pipeline.py --explicar-gosto
```
Ampliar o corpus a partir do metro publicado (a única parte que usa rede):

```bash
# por faixa de poemas
python3 ferramentas/colher.py --faixa /moulavi/shams/ghazalsh/sh 1 150

# por metro: o índice /simi/ do Ganjoor lista todos os poemas de um vazn
python3 ferramentas/colher.py --metro 'فاعلاتن فاعلاتن فاعلن' --paginas 3

# conferir um vazn sem colher nada
python3 engine/metrica.py 'مفتعلن مفاعلن مفتعلن مفاعلن'
```


## Estrutura

| Caminho | O quê |
|---|---|
| `data/aruz_corpus.json` | Versos de Rumi escandidos à mão (a fonte do ritmo) |
| `data/arkan.json` | Os pés do aruz — a tabela que faz o vazn publicado parsear por composição |
| `data/metros_publicados.json` | Padrões de Elwell-Sutton, a segunda fonte que confere a escansão derivada |
| `engine/generative.py` | Motor generativo + relatório de auditoria |
| `engine/ritmo.py` | Operações rítmicas auditáveis (inversão, aumentação, síncope, hoquetus) |
| `engine/export.py` | Exportação MusicXML e MIDI, só com a stdlib |
| `engine/complexidade.py` | Quanto é Rumi, quanto é acaso; medidas de encaixe; compasso natural |
| `engine/filtros.py` | A peneira — e o registro das heurísticas que a medição derrubou |
| `engine/selecao.py` | Partida a frio por medoides; hipóteses sempre rotuladas |
| `engine/gosto.py` | Ranqueador aprendido do julgamento do autor, com pesos legíveis |
| `engine/metrica.py` | O vazn publicado vira escansão, com portão de fonte dupla |
| `engine/pipeline.py` | Os dez estágios encadeados, do verso à partitura |
| `ferramentas/colher.py` | Colhe corpus do Ganjoor em lote (a única parte com rede) |
| `app/server.py` · `app/index.html` | Servidor local e interface de co-produção |
| `tests/` | Garantia de auditabilidade (54 testes) |
| `handout/HANDOUT.md` | Handout completo do projeto |
| `docs/PROCESSO_INTERFACE.md` | Desenho do processo da interface |
| `docs/PIPELINE.md` | O pipeline, o funil e as quatro heurísticas derrubadas |
| `docs/CORPUS.md` | Ampliar o corpus: o vazn publicado, a fonte dupla, e o que o lote não pode afirmar |
| `docs/PROPOSTA_divan_2214.md` | A correção filológica do verso do Divã (aplicada) |

## Como escolher entre milhões de melodias

O motor gera centenas de milhões de sequências de nota a partir de 21 segundos de
Rumi, e **não existe regra que substitua o ouvido do autor**: quatro heurísticas
propostas para filtrar foram derrubadas pela medição (ver `docs/PIPELINE.md`). A
peneira rejeita só o degenerado — 0,07%. O resto é escolha humana, apoiada por um
ranqueador que aprende de comparações A/B, mantém os pesos legíveis em português
e avisa quando não sabe. Cerca de **40 comparações** bastam; depois disso o ganho
estaciona.

## O compasso do aruz

O pé do ramal (`fāʿilātun`, `–u––`) dura 3,5 quarters — sete colcheias, **7/8**. Em
4/4 ele desliza contra a barra: a consistência de groove do Masnavi cai de 1,00 para
0,56, *abaixo* do acaso. O exportador usa o compasso que o pé pede, e `--compasso`
permite escolher outro. A seção 4 do handout já listava 7/8 entre as métricas do Clube
da Esquina: é onde a métrica persa e a estética brasileira do projeto se encontram.

## Recursos opcionais

**Nada é necessário para o básico** — motor, app, operações rítmicas, complexidade e
exportação MusicXML/MIDI rodam só com a stdlib. Opcionais em
`requirements-opcionais.txt`: `music21` e `muspy` (leves, para checagem cruzada da
partitura e das métricas), LilyPond e fluidsynth (sistema, para PDF e áudio), e
`musicntwrk` (pesada — puxa tensorflow e librosa; é dela que vem a licença GPL).

## Direitos

Texto de Rumi em domínio público. Traduções de referência: apenas Nicholson e
Whinfield (domínio público). Letra em português: recriação própria. Música:
original. Não é parecer jurídico — ver `handout/HANDOUT.md`, seção 7.

## Licença

Código sob **GPL-3.0** (ver `LICENSE`). O projeto era MIT até o commit `91b2a8f`;
a mudança veio da integração com a [musicntwrk](https://github.com/marcobn/musicntwrk),
que é GPL-3.0 e estende a licença à obra combinada. Quem obteve uma versão anterior
segue com os direitos que o MIT concedeu naquela versão — ver `LICENSE.historico`,
e o texto MIT original em `LICENSE.MIT`.

Isso vale para o **código**. O conteúdo textual e musical autoral (letra em
português, melodia, harmonia, arranjo) tem licença separada: CC BY-SA 4.0
(sugestão; ajuste conforme sua escolha). O texto persa de Rumi é domínio público e
a escansão métrica é fato linguístico, não protegível.
