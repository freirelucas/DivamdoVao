# Proposta: corrigir a identificação e a escansão do verso `divan_2214`

**Status: proposta. Nada foi alterado no corpus.** Os campos `metro` e `escansao`
do verso seguem como estavam; a proposta está registrada ao lado, em
`_proposta_metro` e `_proposta_escansao`, e só entra em vigor com o aval do autor.

---

## 1. O que o corpus afirma hoje

```json
"id": "divan_2214",
"obra": "Divã de Shams, gazal 2214 (abertura)",
"metro": "ramal_mahzuf",
"persa": "آن نفسی که با خودی یار چو خار آیدت",
"escansao": ["–","u","–","–","u","–","–","–","u","–","–","–","u","–"]
```

O próprio corpus já anotava, em `_nota`, que a escansão era "aproximada para fins
de protótipo". Duas verificações independentes mostraram que o problema é maior
que aproximação.

## 2. Como a divergência apareceu

**Verificação estrutural.** `conferir_metro()` decompõe a escansão nos pés do metro
declarado. O ramal tem pé `–u––`. Os pés 2 e 3 deste verso saem como `u–––` — que é
exatamente o pé do **hazaj** (`mafāʿīlun`), já declarado no mesmo arquivo. Cinco
divergências no total. Ou o rótulo do metro está errado, ou a escansão está.

**Verificação estatística — que NÃO decide.** Testei a periodicidade do pé contra
4000 embaralhamentos das mesmas durações. `masnavi_1` e `masnavi_2` dão p≈0,016: o
pé do ramal aparece claramente acima do acaso. Este verso dá **p=0,072** na escansão
atual e **p=0,10** na proposta abaixo. Com 14 símbolos e três valores de duração, o
nulo por embaralhamento não tem poder para distinguir as duas hipóteses. **A
estatística não sustenta a correção, e é preciso dizer isso**: a evidência a favor
é filológica.

## 3. O que a fonte diz

O verso **não é o gazal 2214**. A linha `آن نفسی که با خودی یار چو خار آیدت` abre o
**gazal 323** do Divã de Shams na numeração do Ganjoor — cujo gazal 2214 começa com
outro verso inteiramente (`خنک آن دم که نشینیم در ایوان، من و تو`).

E o vazn que a fonte registra para o gazal 323 é:

> مفتعلن مفاعلن مفتعلن مفاعلن — **رجز مثمن مطوی مخبون**
>
> *moftaʿelon mafāʿelon moftaʿelon mafāʿelon* = rajaz mosamman matvi makhbun

Não é ramal. É rajaz de oito pés, com os pés **alternando** entre a forma *matvi*
(`–uu–`) e a *makhbun* (`u–u–`).

*Fonte:* Ganjoor, gazal 323 — https://ganjoor.net/moulavi/shams/ghazalsh/sh323

## 4. A escansão proposta

Aplicando as regras padrão de quantidade silábica do persa — CV = curta (`u`);
CVV ou CVC = longa (`–`); CVVC ou CVCC = **superlonga** (`=`, que vale longa + curta):

```
ān  na  fa  sī  ke  bā  xo  dī  yār  čo  xār  ā  ya  dat
 –   u   u   –   u   –   u   –   =   u    =   –   u   –
```

`yār` e `xār` são CVVC, portanto superlongas. Expandindo cada superlonga nas suas
duas posições métricas, a escansão dá 16 posições que casam com o vazn **pé a pé**:

| Pé | Esperado | Encontrado | Sílabas |
|---|---|---|---|
| 1 | `–uu–` | `–uu–` | ān na fa sī |
| 2 | `u–u–` | `u–u–` | ke bā xo dī |
| 3 | `–uu–` | `–uu–` | yār čo xār |
| 4 | `u–u–` | `u–u–` | xār ā ya dat |

`xār` atravessa a fronteira entre os pés 3 e 4 — que é precisamente o que uma
sílaba superlonga faz. Conferido por `conferir_metro()`: **16/16 posições, 4/4 pés**.

## 5. O que muda, na prática

- **5 das 14 posições** da escansão.
- **A duração total não muda**: 12.0 quarters nos dois casos. Muda o ritmo por dentro.
  - atual: `1.0 0.5 1.0 1.0 0.5 1.0 1.0 1.0 0.5 1.0 1.0 1.0 0.5 1.0`
  - proposta: `1.0 0.5 0.5 1.0 0.5 1.0 0.5 1.0 1.5 0.5 1.5 1.0 0.5 1.0`
- A proposta usa a **superlonga** (1.5 quarters) pela primeira vez no corpus. O
  símbolo está definido em `DUR_ARUZ` e documentado desde o início, mas nenhum
  verso o exercia.
- O `id` e o campo `obra` também estariam errados: seria o gazal **323**, não 2214.

## 6. Para aprovar

Trocar, no verso, `metro` por `rajaz_mosamman_matvi_makhbun` (já registrado em
`metros`), `escansao` pela proposta, `obra` pela referência ao gazal 323, e marcar
`metro_conferido: true`. É um commit de poucas linhas, e o teste
`test_metro_confere_com_escansao` passa a exigir conformidade em vez de exigir a
marca de divergência.

## 7. O que ainda falta para ficar definitivo

A numeração do Ganjoor é amplamente usada, mas a referência canônica é a edição
**Foruzanfar**, que não consultei diretamente — a concordância em
dar-al-masnavi.org/ghazals-foruz.html estava atrás de verificação de acesso. Antes
do uso final, conferir o número do gazal e o vazn contra Foruzanfar. A escansão
proposta não depende dessa conferência (ela deriva do vazn e das regras de
quantidade), mas o `id` e a atribuição dependem.
