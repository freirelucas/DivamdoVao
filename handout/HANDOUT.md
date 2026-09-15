# Divã do Vão — Handout do Projeto

*Da rítmica de Rumi (aruz persa) à canção, com colorido Clube da Esquina e auditabilidade de ponta a ponta.*

---

## 1. O que é

Divã do Vão é uma **ferramenta de co-produção musical** e um **ciclo de canções**. Parte da obra de Rumi (séc. XIII, domínio público) e a transforma em música por um processo em que:

1. a **rítmica** da melodia é derivada da métrica quantitativa do persa original (o *aruz*), não inventada;
2. a **harmonia e a cor** seguem a linguagem do Clube da Esquina (modos, tensões, baixos móveis);
3. a **tradução para o português** é feita em **interação com o usuário**, ajustando as sílabas às durações;
4. cada decisão é **auditável**: toda nota rastreia até a sílaba persa que a originou.

Não é geração de "música por IA" como caixa-preta. É um instrumento onde o material de Rumi é o motor e o humano co-produz.

---

## 2. Por que o aruz é o motor

Rumi escreveu em **persa** (não árabe, embora o sistema métrico persa derive do árabe). A poesia persa clássica é **quantitativa**: sílabas são curtas, longas ou superlongas, e o metro é um padrão fixo dessas durações. O Masnavi usa o metro **ramal** (`fāʿilātun` repetido).

Isso tem consequência musical direta e antiga: **o padrão de sílabas longas e curtas já é o ritmo de uma canção** — na música persa clássica, saber quando estender uma nota decorre do metro do texto. Nós adotamos exatamente essa ponte:

| Símbolo aruz | Sílaba | Duração musical (4/4) |
|---|---|---|
| `–` | longa | semínima (1.0) |
| `u` | curta | colcheia (0.5) |
| `=` | superlonga | semínima pontuada (1.5) |

**Exemplo — abertura do Masnavi** (`bešnaw az nay čun hekāyat mī-konad`):

```
beš  naw  az  nay  čun  he  kā  yat  mī  ko  nad
 –    u   –   –    –    u   –   –    –   u   –
1.0  0.5 1.0 1.0  1.0  0.5 1.0 1.0  1.0 0.5 1.0   (quarters)
```

Regra aplicada: a última sílaba do hemistíquio conta sempre como longa.

*Fontes de escansão:* Wikipedia "Persian metres"; persianlanguageonline.com (aruz, parte 1); ScienceDirect "Prosody recognition in Persian poetry" (o padrão longo/curto forma o ritmo da canção). Escansões no corpus são de protótipo; conferir com edição crítica (Foruzanfar) antes do uso final.

---

## 3. Explorações rítmicas previstas

O aruz dá o material; a co-produção o explora. Operações rítmicas já suportadas ou planejadas:

- **Derivação direta** — durações 1:1 do metro (base, implementada).
- **Inversão métrica** — trocar longas↔curtas para gerar uma variação-espelho (a mesma frase "ao contrário", útil para pontes e contracantos).
- **Aumentação / diminuição** — multiplicar todas as durações (×2 para clímax lento, ÷2 para transe).
- **Deslocamento (síncope)** — deslocar o padrão contra o tempo forte, o "suingue" que aproxima do partido-alto brasileiro.
- **Sobreposição** — o mesmo metro em duas vozes defasadas (hoquetus), evocando o coro dervixe.

Cada operação é uma função pura sobre a lista de durações do aruz — e cada uma preserva o rastro de auditoria.

---

## 4. Colorido Clube da Esquina

A cor é dada por escolhas harmônicas e de arranjo, não por citação (linguagem estética não se protege):

- **Modos**: dórico (menor com 6ª maior, o tom mineiro), lídio (brilho), mixolídio, eólio.
- **Tensões**: acordes maj7, 9, 11/13; baixos que descem por graus como assinatura.
- **Métrica que respira**: 6/8, 3/4, 4/4 suingado, 7/8.
- **Timbres**: piano e violão em diálogo de registro (um agudo/rítmico, outro grave/sustentado, trocando por seção), agbê, vozes em terças.

---

## 5. Arquitetura

```
diva-repo/
├── data/aruz_corpus.json     # versos de Rumi escaneados (a FONTE do ritmo)
├── engine/generative.py      # motor: aruz -> ritmo -> melodia modal + auditoria
├── app/server.py             # servidor local (stdlib), API do motor
├── app/index.html            # interface de co-produção
├── tests/                    # garantia de auditabilidade (5 testes)
├── docs/PROCESSO_INTERFACE.md# desenho do processo da interface
├── handout/HANDOUT.md        # este documento
└── README.md
```

**Fluxo de dados:** `corpus (aruz)` → `durar_por_aruz()` → `gerar_melodia(modo, entropia)` → `relatorio_auditoria()` → interface/partitura. Semente textual fixa ⇒ resultado reprodutível (requisito de auditoria).

---

## 6. Auditabilidade — o compromisso central

Toda saída do motor vem acompanhada de um **relatório de auditoria** que responde, para cada nota: *qual sílaba persa a originou, qual símbolo métrico, e por que ela dura o que dura*. Os testes em `tests/` verificam três invariantes:

1. **duração deriva do aruz** (nunca inventada);
2. **alinhamento sílaba↔nota** (uma sílaba, uma nota; melisma só explícito);
3. **reprodutibilidade** (mesma semente, mesma melodia).

Isso torna o processo inspecionável por um músico, um revisor ou o próprio autor — e distingue o projeto de geradores opacos.

---

## 7. Direitos autorais

- **Texto persa de Rumi**: domínio público (morte em 1273).
- **Escansão métrica**: fato linguístico, não protegível.
- **Traduções de referência**: usar apenas Nicholson (†1945) e Whinfield (†1922), em domínio público. **Não** partir das versões de Coleman Barks (protegidas), nem de Arberry (protegido até ~2040).
- **Letra em português**: recriação própria, obra derivada original.
- **Música**: melodia (ritmo do aruz + alturas modais), harmonia e arranjo, 100% originais.

*Não é parecer jurídico. Uso comercial (fonograma, sincronização) pede validação de advogado de direito autoral.*

---

## 8. Roteiro (do repositório ao disco)

1. **MVP local** (este repositório): motor + app + auditoria + 3 versos escaneados.
2. **Ampliar o corpus**: mais ghazais escaneados e conferidos (Foruzanfar).
3. **Operações rítmicas**: implementar inversão, aumentação, síncope, hoquetus como funções auditáveis.
4. **Co-produção de letra**: editor que valida sílaba↔duração em tempo real e sugere elisões.
5. **Arranjo**: exportar partitura (LilyPond) e maquete (fluidsynth) por canção.
6. **Sessão**: gravar com músicos as canções aprovadas; registrar atribuição.

---

## 9. Como rodar

```bash
python3 app/server.py          # http://localhost:8000
python3 tests/test_auditabilidade.py   # 5/5 esperado
python3 engine/generative.py --verso masnavi_1 --modo dorico
```

Requisitos: Python 3.10+ (stdlib). Para partitura/áudio: `music21`, LilyPond, fluidsynth (opcionais, ver README).
