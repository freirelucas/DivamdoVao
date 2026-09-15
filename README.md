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
python3 tests/test_auditabilidade.py      # esperado: 5/5

# 3. gerar uma melodia por linha de comando
python3 engine/generative.py --verso masnavi_1 --modo dorico
```

## Estrutura

| Caminho | O quê |
|---|---|
| `data/aruz_corpus.json` | Versos de Rumi escaneados (a fonte do ritmo) |
| `engine/generative.py` | Motor generativo + relatório de auditoria |
| `app/server.py` · `app/index.html` | Servidor local e interface de co-produção |
| `tests/` | Garantia de auditabilidade (5 testes) |
| `handout/HANDOUT.md` | Handout completo do projeto |
| `docs/PROCESSO_INTERFACE.md` | Desenho do processo da interface |

## Recursos opcionais (partitura e áudio)

O básico roda só com a stdlib. Para exportar partitura e maquete de áudio:

```bash
pip install music21
# LilyPond e fluidsynth via gerenciador de pacotes do sistema
```

## Direitos

Texto de Rumi em domínio público. Traduções de referência: apenas Nicholson e
Whinfield (domínio público). Letra em português: recriação própria. Música:
original. Não é parecer jurídico — ver `handout/HANDOUT.md`, seção 7.

## Licença

Código sob MIT (ver `LICENSE`). Conteúdo textual/musical autoral: CC BY-SA 4.0
(sugestão; ajuste conforme sua escolha).
