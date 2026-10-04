# Ampliar o corpus — do vazn publicado ao verso que o motor toca

O projeto tinha **três versos**. Não por falta de fonte: a obra de Rumi é
imensa e está em domínio público. Por causa do gargalo da escansão — marcar
sílaba por sílaba qual é longa, curta ou superlonga é trabalho filológico, e
feito à mão não escala.

Este documento registra como esse gargalo caiu, **o que a ingestão em lote
pode afirmar, e o que ela não pode.**

---

## 1. A medição que dispensou o trabalho caro

Antes de construir qualquer coisa, a pergunta: a escansão declarada nos três
versos acrescenta informação além do metro?

```
masnavi_1    metro prevê: –u–––u–––u–        corpus tem: –u–––u–––u–        idêntico
masnavi_2    metro prevê: –u–––u–––u–        corpus tem: –u–––u–––u–        idêntico
divan_2214   metro prevê: –uu–u–u––uu–u–u–   corpus tem: –uu–u–u––uu–u–u–   idêntico
```

**Zero informação nova por verso.** A escansão é o metro reescrito. Então o
trabalho não é escandir verso: é saber o metro. E o metro é publicado.

---

## 2. O vazn não é um rótulo — é a escansão em nomes de pés

Para cada poema, o Ganjoor registra um vazn:

```
مفتعلن مفاعلن مفتعلن مفاعلن  (رجز مثمن مطوی مخبون)
```

Isso não é um nome opaco. É uma sequência de **pés** (*arkān*), e cada pé é
uma palavra-mnemônica derivada da raiz árabe فعل cuja **própria quantidade
silábica é o padrão que ela nomeia**:

| pé | sílabas | quantidade |
|---|---|---|
| `مفتعلن` moftaʿelon | mof · ta · ʿe · lon | `–` `u` `u` `–` |
| `مفاعلن` mafāʿelon | ma · fā · ʿe · lon | `u` `–` `u` `–` |

Concatenando: `–uu–` + `u–u–` + `–uu–` + `u–u–` = `–uu–u–u––uu–u–u–`, que é
**exatamente** a escansão do `divan_2214`.

O vazn parseia por composição. Conferir ~26 pés uma vez serve milhares de
poemas. É isso que torna o lote possível (`data/arkan.json`).

---

## 3. Fonte dupla, porque a leitura tem ambiguidade real

Ler a quantidade da palavra-mnemônica não é mecânico. Sem diacríticos, `فعلن`
é *faʿlon* (`– –`) ou *faʿalon* (`u u –`) — e **as duas existem** como pé
final de metros reais (محذوف contra مقصور/اصلم). A grafia do Ganjoor não
distingue.

Resolver isso por intuição repetiria o erro que
[`engine/filtros.py`](../engine/filtros.py) registra: ancorar heurística numa
autoridade inventada. Então não se resolve por intuição.

```
    vazn do Ganjoor  ──▶  pés (data/arkan.json)  ──▶  escansão candidata
                                                             │
                     data/metros_publicados.json  ──▶  CASA?  │
                     (Elwell-Sutton: 32 padrões,            ╱ │ ╲
                      com código e frequência)             ╱  │  ╲
                                                      uma  duas  nenhuma
                                                        │    │     │
                                                  RESOLVIDO  │  QUARENTENA
                                                             │   (fora do
                                                         PENDENTE  corpus,
                                                      (1 decisão   com o
                                                       humana por  motivo
                                                          metro)   nomeado)
```

O portão está em [`engine/metrica.py`](../engine/metrica.py)
(`resolver_vazn`). **Nada entra adivinhado.**

Confirmação de bônus: a correção filológica feita antes neste projeto —
`divan_2214` reatribuído ao gazal 323, metro *rajaz mosamman matvi makhbun* —
casa com **Rajaz 5.2.16** na tabela de Elwell-Sutton (0,8% do corpus persa).
O masnavi é **Ramal 2.4.11**. A correção se sustenta contra fonte externa
independente.

---

## 4. Cobertura: dois números, os dois verdadeiros

| medida | valor | o que significa |
|---|---|---|
| por **fórmula de vazn** | 39 de 212 = **18,4%** | o inventário completo do Ganjoor tem 212 fórmulas; a tabela publicada que serve de segunda fonte traz 32 padrões — **os frequentes** |
| por **poema** | **~96%** | Rumi usa justamente os frequentes. Em amostra aleatória de 70 gazais do Divã de Shams, 65 de 68 com vazn resolveram |

Citar só o 18,4% sugeriria que a ingestão não funciona; citar só o ~96%
esconderia que a tabela de padrões é estreita. **O que decide se há corpus é
o segundo**; o que diz quanto falta para o corpus ser completo é o primeiro.

O que restringe não são os pés (só 9 fórmulas caem por pé ausente) — é a
tabela de 32 padrões publicados. Ampliar a cobertura é tarefa **delimitada e
medível**: a quarentena nomeia exatamente o pé ou o padrão que falta.

### Pés deixados de fora de propósito

`مستفعل`, `متفعلن`, `فاع`, `مفاعل`, `فاعل` — a leitura de cada um admite mais
de uma interpretação que não sei desempatar. **Um pé com padrão errado é mais
perigoso que um pé ausente:** se por azar a escansão errada casar com um
padrão publicado, o portão de fonte dupla confirma uma falsidade. Pé ausente
manda o metro para quarentena *nomeando o pé*, o que é acionável.

---

## 5. O que a ingestão em lote NÃO pode afirmar

Três limites, declarados em vez de escondidos.

**a) Onde ficam as superlongas.** O metro fixa as **posições** métricas; não
fixa onde duas posições se fundem numa sílaba superlonga, porque isso depende
das palavras. O `divan_2214` mostra o caso: o corpus traz 14 sílabas
(`–uu–u–u–=u=–u–`, superlonga em *yār* e *xār*) e o vazn dá 16 símbolos
simples. **Expandidos, são as mesmas 16 posições, e a duração total é
idêntica** (`=` vale 1,5, igual a `–` mais `u`). Muda o agrupamento: uma nota
de 1,5 ou duas de 1,0 e 0,5. Verso ingerido sai com
`superlongas_conferidas: false`.

**b) Qual sílaba persa originou cada nota.** O Ganjoor publica o texto persa,
não a transliteração silabada. Sem ela, o rastro de auditoria rotula
**posição métrica** — `·1`, `·2` — e o relatório declara
`silabas_conferidas: false` com o motivo por escrito. O rastro continua
honesto e completo: diz que a nota dura 1,0 porque a posição 3 do metro
declarado é longa, o que é afirmação sobre a fonte. Só não diz uma palavra que
ninguém conferiu. Transliteração **parcial é recusada**, não completada: meia
lista alinharia nota à sílaba errada.

**c) Qual edição do texto.** O texto colhido segue a edição do Ganjoor, que
**não é a de todo verso do corpus feito à mão**. A abertura do Masnavi:

| fonte | texto |
|---|---|
| corpus (`masnavi_1`/`masnavi_2`) | بشنو از نی چون **حکایت** می‌کند / از جدایی‌ها **شکایت** می‌کند |
| Ganjoor | بشنو این نی چون **شکایت** می‌کند / از جدایی‌ها **حکایت** می‌کند |

`این نی` contra `از نی`, e *hekāyat*/*šekāyat* **trocados entre os
hemistíquios**. As duas são edições legítimas (o corpus segue Nicholson, a
edição crítica em domínio público que o projeto adota) e **escandem igual**.
A variante fica registrada em `_origem.edicao`, não harmonizada à força.

---

## 6. Como colher

A rede vive em [`ferramentas/colher.py`](../ferramentas/colher.py), **fora de
`engine/`**. `engine/` é offline e determinístico: mesma entrada, mesma saída.
Misturar rede faria o corpus mudar sozinho e quebraria a reprodutibilidade que
o projeto promete. Um teste trava isso (`test_engine_inteiro_fica_offline`).

```bash
# por faixa de poemas
python3 ferramentas/colher.py --faixa /moulavi/shams/ghazalsh/sh 1 150

# por METRO: o índice /simi/ lista todos os poemas que compartilham um vazn,
# então um metro resolvido uma vez serve o lote inteiro
python3 ferramentas/colher.py --metro 'مفتعلن مفاعلن مفتعلن مفاعلن (رجز مثمن مطوی مخبون)' --paginas 3

# um poema, sem gravar
python3 ferramentas/colher.py --url /moulavi/shams/ghazalsh/sh323 --seco
```

Saída: `data/corpus_colhido.json` (pronto para o motor) e
`data/corpus_colhido_quarentena.json` (**o mapa do que falta**).

**Polidez.** O `robots.txt` do Ganjoor (04/10/2026) bloqueia `/User/`,
`/Admin/` e login; páginas de poema são liberadas. Mesmo assim: cache em disco
para nunca pedir duas vezes a mesma página, espera entre pedidos, um pedido
por vez, e `User-Agent` que diz quem somos e para quê. Colher é pedir um favor
a um acervo mantido por voluntários. O cache também é o que permite mexer na
tabela de pés e remedir tudo **sem pedir nada ao servidor outra vez**.

---

## 7. O esforço humano, medido

O que a ingestão em lote **não** pede ao autor:

- escandir verso — derivado do vazn publicado;
- conferir poema — conferido por fonte dupla;
- atribuir metro — vem do Ganjoor, confirmado por Elwell-Sutton.

O que ela **pede**, e só isso:

- decidir um metro **pendente**, quando duas leituras publicadas empatam —
  uma decisão por metro, herdada por todos os poemas daquele metro (na amostra
  de 70 gazais: **zero** pendências);
- escrever a `assinatura_afetiva` de cada metro novo, que é leitura do autor
  sobre o caráter do metro e **não** é derivável da fonte — a máquina deixa o
  campo ausente de propósito;
- e, quando quiser afirmar mais sobre um verso específico: transliteração
  silabada, glosa, imagem. Cada verso colhido lista isso em
  `_pendencias_humanas`.

Nada dessas pendências impede o motor de rodar. Todas mudam o que o projeto
pode **afirmar** sobre o verso — e é por isso que ficam escritas no próprio
verso em vez de serem silenciosamente preenchidas.
