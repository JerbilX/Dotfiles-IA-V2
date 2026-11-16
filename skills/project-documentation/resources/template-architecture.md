# Arquitectura y Diseño del Sistema (Architecture)

Documento explicativo de los principios fundamentales de diseño, modelo conceptual, esquemas de datos y mecanismos de extensibilidad del proyecto.

---

## 1. Filosofía y Principios de Diseño

El sistema está construido bajo principios de desacoplamiento modular, determinismo e inmunidad normativa:

- **Desacoplamiento Modular:** Separación estricta entre directivas agnósticas (core), adaptadores de runtime y habilidades especializadas bajo demanda (skills).
- **Inmutabilidad y Determinismo:** Las operaciones de generación y compilación son repetibles e idempotentes; los respaldos automáticos garantizan reversibilidad total.
- **Mínima Intervención (Minimal Blast Radius):** Cada cambio se resuelve en el nivel más bajo posible de la jerarquía (Nivel 0 CLI $\rightarrow$ Nivel 1 Tooling $\rightarrow$ Nivel 2 Skills $\rightarrow$ Nivel 3 Rules $\rightarrow$ Nivel 4 Core).

---

## 2. Mapa Modular del Repositorio

```
<repo-root>/
├── core/                  # Componentes y directivas transversales agnósticas
├── runtimes/              # Adaptadores y configuraciones por entorno
│   ├── schema/            # Esquemas de validación declarativa (JSON Schema)
│   └── <runtime-name>/    # Reglas y manifiesto específico del runtime
├── skills/                # Catálogo canónico de habilidades especializadas
├── docs/                  # Documentación modular (Diátaxis)
│   ├── setup.md           # Guía de aprovisionamiento y entorno
│   ├── cli.md             # Referencia técnica de comandos
│   ├── architecture.md    # Este documento explicativo
│   └── adr/               # Registro de decisiones arquitectónicas (MADR)
├── build.sh               # Orquestador del ciclo de compilación y verificación
└── README.md              # Contrato minimalista de entrada
```

---

## 3. Esquemas de Datos y Contratos de Configuración

Las configuraciones declarativas se validan formalmente contra esquemas JSON estándar (`JSON Schema Draft-07`):

### Esquema de Configuración (`runtime-config.schema.json`)
Gobierna la estructura requerida para los manifiestos de runtime:
- `skills`: Lista de habilidades habilitadas para el runtime.
- `binaries`: Mapa de alias a binarios o scripts ejecutables.
- `target`: Diccionario con rutas canónicas de destino en el sistema anfitrión (`config_dir`, `prompt_filename`, `skills_dir`).

---

## 4. Guía de Extensibilidad: Cómo Añadir un Nuevo Componente

Incorporar un nuevo módulo o adaptador al sistema es 100% declarativo:

1. **Crear Directorio:** Crear la estructura correspondiente en `runtimes/<nuevo-módulo>/`.
2. **Definir Manifiesto:** Crear `runtimes/<nuevo-módulo>/config.json` cumpliendo el esquema canónico.
3. **Validar Integridad:** Ejecutar `./build.sh check <nuevo-módulo>` para auditar consistencia sintáctica.
4. **Compilar y Probar:** Ejecutar `./build.sh build <nuevo-módulo>` para generar los artefactos finales.
