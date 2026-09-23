# O pipeline — do verso de Rumi à partitura

```
 0  FONTE        data/aruz_corpus.json          verso persa + escansão do aruz
 1  CONFERIR     conferir_metro()               a escansão casa com o metro declarado?
 2  DURAR        durar_por_aruz()               escansão -> durações
 3  OPERAR       engine/ritmo.py                inversão, aumentação, deslocamento…
 4  GERAR        gerar_melodia()                N candidatas
────────────────────────────────────────────────────────────  barato, automático
 5  PENEIRAR     engine/filtros.py              só o degenerado (~0,07%)
 6  MEDIR        engine/complexidade.py         decomposição, MIR, encaixe
 7  LOTE/ORDENAR engine/selecao.py · gosto.py   medoides, ou o gosto aprendido
────────────────────────────────────────────────────────────  caro: escuta humana
 8  JULGAR       comparação A/B                 treina o gosto
 9  LETRAR       ajuste_prosodico()             letra PT validada contra o aruz
10  EXPORTAR     engine/export.py               MusicXML + MIDI + auditoria
```

A linha divisória é o desenho inteiro: tudo à esquerda é barato e automático, e
o pipeline existe para empurrar o máximo de trabalho para lá, porque o que custa
é o ouvido do autor.

## Como rodar

```bash
python3 engine/pipeline.py --verso masnavi_1 --n 300 --lote 8
python3 engine/pipeline.py --verso masnavi_1 --julgar 40      # laço A/B
python3 engine/pipeline.py --explicar-gosto
python3 engine/pipeline.py --verso divan_2214 --export musicxml,midi
```

Ou pela interface: `python3 app/server.py`, card "Julgar candidatas".

## O tamanho do problema

| | |
|---|---|
| material de Rumi no corpus | 3 versos, 36 sílabas, **21 segundos** |
| sequências de nota distintas que o motor pode emitir | ~590 milhões por modo |
| tocadas em sequência | milhares de anos |
| o que a peneira corta | **0,07%** |
| o que a escuta humana alcança numa vida (8 h/dia, 60 anos) | **0,6%** |

Não há atalho automático que substitua a escuta. É isso que o estágio 8 resolve,
e por isso ele é o único que produz verdade neste projeto.

## O que cada estágio pode afirmar

| estágio | afirma | não afirma |
|---|---|---|
| 0-4 | derivação auditável da fonte, nota a nota | nada sobre qualidade |
| 5 | "isto não é melodia" | "isto é melodia ruim" |
| 6 | descrição (entropia, groove, complexidade efetiva) | ordenação — a fração Rumi/acaso é constante dentro do espaço |
| 7 sem julgamento | **cobertura**: o lote representa o espaço | qualidade |
| 7 com julgamento | ordenação pelo gosto aprendido, com confiança declarada | certeza — `confianca()` avisa quando estaciona |
| 8 | o que o autor prefere | que o modelo já saiba |

O campo `motivo_da_ordem` acompanha cada candidata até o arquivo exportado, para
que a saída nunca deixe dúvida sobre qual dos dois casos está em jogo.

## Quatro heurísticas que a medição derrubou

Este é o resultado mais útil desta etapa, e está gravado também no docstring de
`engine/filtros.py` para que ninguém o refaça.

| # | proposta | o que a medição mostrou |
|---|---|---|
| 1 | cinco filtros de "sanidade", reprovando 9 em 10 | Gosto sem dados. "Sem salto > 5 semitons" cortava 32,5% para remover o que já era 3,98% dos intervalos. "Termina na tônica" cortava 66,6%, jogando fora dois dos três fechos que o próprio motor faz de propósito. |
| 2 | alvo de 0,72 de reversão após salto (von Hippel & Huron) | Norma de música clássica ocidental, e os próprios autores avisam que pode ser artefato de âmbito — o nosso tem 6 alturas. |
| 3 | usar `exemplos/*.musicxml` como perfil "do autor" | Autoria inventada: o campo `composer` diz "Divã do Vão", que é o nome do projeto; os arquivos foram gerados por music21; e `exemplos/README.md` já registrava que não são saída deste motor. |
| 4 | lote inicial "diverso" por k-center | **26% pior que sorteio aleatório**: k-center escolhe extremos, e extremos cobrem mal o miolo. |

O padrão nas quatro é o mesmo: buscar uma autoridade externa — intuição, norma
publicada, autoria suposta, diversidade vaga — em vez de aceitar que **ainda não
existe verdade de referência neste projeto**.

O que sobrou, medido: **medoides** (k-means++ e a candidata real mais próxima de
cada centro) cobre o espaço 13% a 17% melhor que o sorteio aleatório, em lotes de
4 a 20. É afirmação sobre cobertura, não sobre qualidade.

## Duas hipóteses em teste

Derivam do material que o corpus declara, não de norma nenhuma. Aparecem sempre
rotuladas, da CLI ao JSON exportado.

- **eco entre pés** — o contorno do pé 2 ecoar o do pé 1. Os pés são de Rumi.
- **estável em longa** — grau de tônica, terça ou quinta caindo em sílaba longa.

Que ordenar por elas produza música melhor é hipótese, e os julgamentos do autor
confirmam ou matam cada uma. Se matarem, viram o quinto item da tabela acima.

## Um defeito do gerador, não da seleção

O contorno do pé 2 repetia o do pé 1 em 5,81% dos casos contra 3,70% por acaso: o
ritmo deriva dos pés do aruz, mas a melodia era cega a eles. **Não se seleciona o
que nunca é gerado** — nenhum ranqueador produziria coerência motívica num espaço
que não a contém.

`gerar_melodia(motivico=True)` faz o segundo pé reusar os passos do primeiro,
perturbados por `entropia`. O eco exato vai de 5,6% para 25,5%. Fica desligado
por padrão: é mudança de caráter musical, não correção de auditoria.

## Quantos julgamentos bastam

Medido em simulação com gosto sintético linear e ruído de 15%:

| julgamentos | aleatório | ativo |
|---|---|---|
| 10 | 0,521 | 0,606 |
| 20 | 0,536 | 0,638 |
| 40 | 0,751 | **0,816** |
| 80 | 0,743 | 0,782 |
| 160 | 0,743 | 0,788 |

(tau de Kendall contra o gosto verdadeiro.)

**As duas curvas estacionam a partir de ~40.** O teto é a inconsistência do
julgamento humano, não a falta de dados: pedir 160 comparações desperdiçaria o
tempo do autor sem melhorar a ordenação. Quarenta comparações são cerca de dez
minutos.

A simulação assume que o gosto é linear nos atributos medidos. Se não for, o teto
real é menor — e é `confianca()` que denuncia, em vez de o modelo ranquear com
segurança fingida.
