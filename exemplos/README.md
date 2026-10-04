# Exemplos — procedência

Os dois arranjos deste diretório são o rosto do projeto, e por isso importa dizer
com precisão o que eles são e o que não são.

## O que são

Canções completas e arranjadas, em quatro partes (Voz, dois pianos e Violão),
com letra em português cantável.

| Arquivo | Título | Compassos | Notas na voz | Sílabas de letra |
|---|---|---|---|---|
| `01_casa_de_hospedes.*` | A Casa de Hóspedes | 36 | 175 | 148 |
| `02_dois_numa_alma.*` | Dois numa Alma | 20 | 88 | 74 |

`01` trabalha a imagem da casa de hóspedes, do Masnavi. `02` trabalha o instante
do encontro — "dois numa só alma" — a mesma imagem que o corpus registra no verso
do Divã de Shams (ver `data/aruz_corpus.json`, e a proposta de correção em
`docs/PROPOSTA_divan_2214.md`).

## O que NÃO são

**Não são saída deste motor.** Foram produzidos fora do pipeline, com music21
v10.5.0 (o campo `<software>` dos arquivos registra isso), antes de o repositório
existir na forma atual. Em particular:

- **não têm relatório de auditoria** — não há, para eles, o artefato que liga cada
  nota à sílaba persa que a originou;
- **não têm verso-fonte declarado** em metadado, só a imagem poética em comum;
- **não respeitam 1:1 sílaba↔nota** — 175 notas de voz para 148 sílabas em `01`
  significa melisma, que o princípio 2 de `docs/PROCESSO_INTERFACE.md` trata como
  exceção marcada, e aqui não está marcada.

Um arranjo produzido pelo caminho auditável do repositório sai com o seu
`_auditoria.json` ao lado, sempre (ver `engine/export.py`). Estes não saíram.

## Como ler os arquivos

Os `.musicxml` abrem em MuseScore, Finale, Sibelius ou music21. Os `.mp3` são
maquetes mono de 96 kbps — referência de escuta, não fonograma.

## Direitos

Texto de Rumi em domínio público. Letra em português: recriação própria. Música:
original. Ver `handout/HANDOUT.md` §7.
