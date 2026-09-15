# Processo de desenvolvimento da interface — co-produção humano × máquina

Escopo declarado: uma interface onde o humano parte da rítmica de Rumi (aruz),
gera material musical, **traduz para o português em interação**, e explora
estruturas rítmicas (derivação, inversão, deslocamento), tudo com colorido
Clube da Esquina e **auditabilidade** visível em tela.

---

## 1. Princípios de design

1. **A fonte é sagrada e visível.** O verso persa e sua escansão ficam sempre à vista; nada de ritmo "mágico".
2. **Uma sílaba, uma nota.** A tela reforça a disciplina prosódica; melisma é exceção marcada.
3. **O humano decide, a máquina propõe.** O motor gera opções; o autor aprova, ajusta ou rejeita.
4. **Auditoria em primeiro plano.** O painel "por que a nota dura o que dura" é parte da interface, não um log escondido.
5. **Leve.** HTML/JS puro, sem dependências; roda local em máquina modesta.

---

## 2. Papéis

- **Autor/curador** (você): escolhe versos, modos, aprova a letra.
- **Usuário co-produtor**: traduz e ajusta sílabas em diálogo.
- **Motor generativo**: deriva ritmo do aruz, propõe alturas modais, devolve auditoria.

---

## 3. Fluxo de interação (loop de co-produção)

```
   ┌─────────────────────────────────────────────────────────────┐
   │  A. SELECIONAR VERSO                                          │
   │     mostra: persa (RTL) + escansão colorida + glosa + imagem  │
   └───────────────┬─────────────────────────────────────────────┘
                   ▼
   ┌─────────────────────────────────────────────────────────────┐
   │  B. PARAMETRIZAR                                              │
   │     modo (dórico/lídio/…) · entropia melódica · (semente)     │
   └───────────────┬─────────────────────────────────────────────┘
                   ▼
   ┌─────────────────────────────────────────────────────────────┐
   │  C. GERAR  →  motor deriva ritmo do aruz, sorteia alturas     │
   │     devolve: notas + RELATÓRIO DE AUDITORIA                   │
   └───────────────┬─────────────────────────────────────────────┘
                   ▼
   ┌─────────────────────────────────────────────────────────────┐
   │  D. OUVIR (síntese-guia Web Audio)                           │
   └───────────────┬─────────────────────────────────────────────┘
                   ▼
   ┌─────────────────────────────────────────────────────────────┐
   │  E. TRADUZIR / ESCREVER LETRA  (co-produção)                  │
   │     o autor digita PT sílaba a sílaba;                        │
   │     a tela confere nº de sílabas × nº de notas (aruz)         │
   └───────────────┬─────────────────────────────────────────────┘
                   ▼
             ┌─────────────┐   não casa    ┌───────────────────────┐
             │ F. VALIDAR  │──────────────▶│ ajustar letra OU       │
             │ sílaba↔nota │               │ aplicar operação       │
             └──────┬──────┘               │ rítmica (inversão,     │
                    │ casa                 │ aumentação, síncope)   │
                    ▼                      └───────────┬───────────┘
   ┌─────────────────────────────────────────────────┘             │
   │  G. APROVAR SEÇÃO  → rotula A/B/C, guarda no projeto           │◀┘
   └───────────────┬─────────────────────────────────────────────┘
                   ▼
   ┌─────────────────────────────────────────────────────────────┐
   │  H. EXPORTAR  → partitura (LilyPond) + maquete (fluidsynth)   │
   └─────────────────────────────────────────────────────────────┘
```

O ciclo E→F→(ajuste)→E é o coração da co-produção: a pessoa negocia a tradução
contra a métrica até o português "caber" no ritmo de Rumi.

---

## 4. Telas / componentes (estado atual e planejado)

| Componente | Função | Estado |
|---|---|---|
| Seletor de verso | Escolhe o verso do corpus | **feito** |
| Escansão colorida | Mostra longa/curta por sílaba | **feito** |
| Parâmetros (modo, entropia) | Controla a geração | **feito** |
| Botão Gerar / Tocar | Chama o motor / sintetiza guia | **feito** |
| Painel de auditoria | Liga nota↔sílaba↔duração | **feito** |
| Editor de letra | Digitação em PT | **feito (livre)** |
| Validador sílaba↔nota em tempo real | Conta e sinaliza descasamento por sílaba, sugere elisão | **feito** |
| Selo de escansão conferida | Mostra quando o metro não confere com a escansão | **feito** |
| Operações rítmicas | Inversão / aumentação / diminuição / deslocamento | **feito** |
| Painel de complexidade | Fração Rumi × acaso, medidas de encaixe, compasso natural | **feito** |
| Biblioteca de seções A/B/C | Guarda e reordena seções aprovadas | *planejado* |
| Exportador | Gera .musicxml / .mid | **feito (CLI, só stdlib)**; .pdf *planejado* |

---

## 5. Contrato da API (já implementado)

```
GET  /api/corpus
     → { versos:[{id,obra,persa,silabas,escansao,glosa_pt,imagem}], metros:{…} }

POST /api/gerar   { verso_id, modo, entropia, semente }
     → { notas:[{midi,nome,dur,silaba,aruz}], auditoria:{…}, tonica, modo }
```

A auditoria retornada inclui `conferencia.alinhado` (booleano) — a interface
usa isso para o semáforo de validação.

---

## 6. Roadmap da interface

1. ~~**v0.1**: gerar + ouvir + auditar + escrever letra livre.~~ feito
2. ~~**v0.2**: validador sílaba↔nota em tempo real (semáforo por sílaba).~~ feito
3. ~~**v0.3**: operações rítmicas com trilha de auditoria.~~ feito — falta a prévia sonora de cada operação
4. **v0.4**: biblioteca de seções A/B/C e montagem da forma da canção.
5. **v0.5**: exportação a partir da interface (a CLI já exporta MusicXML e MIDI).
6. **v0.6**: usar as medidas de encaixe para propor candidatas ordenadas, em vez de o autor varrer o espaço à mão.

---

## 7. Critérios de aceite (o que faz a interface "pronta")

- Nenhuma duração aparece sem origem no aruz (verificável no painel).
- O autor consegue traduzir um verso e ver, sem sair da tela, se as sílabas casam.
- Toda seção aprovada guarda: verso-fonte, modo, letra PT, e a auditoria.
- Roda offline em máquina modesta, sem instalar dependências para o básico.
