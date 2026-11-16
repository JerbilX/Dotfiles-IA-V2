---
name: eso-addon-development
description: >-
  Comprehensive guide and operational reference for developing, debugging, and maintaining Elder Scrolls Online (ESO) UI addons using Lua and ESO API. Covers manifest structure, event handling, SavedVariables, GUI/Controls (XML & programmatic), hooking, and LibAddonMenu integration. ACTIVATE whenever creating, refactoring, or debugging ESO addons.
---

# Elder Scrolls Online (ESO) Addon Development Standard

Guía canónica y referencia de arquitectura para el desarrollo de complementos (*AddOns*) de interfaz de usuario en **The Elder Scrolls Online (ESO)** utilizando Lua 5.1 y la API oficial de ZeniMax Online Studios (ZOS).

---

## 1. Anatomía y Estructura de un Addon

El motor de ESO exige que el nombre del directorio del addon coincida **exactamente** con el nombre del archivo de manifiesto `.txt`.

```
AddOns/<AddonName>/
├── <AddonName>.txt       # Manifiesto obligatorio leído por el motor
├── <AddonName>.lua       # Punto de entrada / inicialización
├── <AddonName>.xml       # Definición de controles UI (TopLevelControl / Templates)
├── bindings.xml          # Definición de atajos de teclado (Keybinds)
├── src/                  # Módulos organizados por responsabilidad
│   ├── Constants.lua
│   ├── Settings.lua      # Configuración y menú LibAddonMenu
│   ├── Events.lua        # Controladores de eventos del juego
│   └── UI.lua            # Lógica y renderizado de interfaz
└── libs/                 # Librerías embebidas (ej. LibAddonMenu-2.0)
```

### Contrato del Manifiesto (`<AddonName>.txt`)
El archivo de manifiesto declara metadatos, dependencias y la lista ordenada de archivos a cargar:

```ini
## Title: Mi Addon Genial
## APIVersion: 101044
## Version: 1.0.0
## Author: MiNombre
## Description: Descripción concisa del addon.
## SavedVariables: MiAddon_SavedVariables
## DependsOn: LibAddonMenu-2.0>=36

# Lista de archivos en orden estricto de carga
bindings.xml
src/Constants.lua
src/Settings.lua
<AddonName>.lua
<AddonName>.xml
```

> [!IMPORTANT]
> - `## APIVersion`: Debe coincidir con la versión actual del cliente (o incluir múltiples versiones separadas por espacio si es retrocompatible).
> - `## SavedVariables`: Declara el identificador global bajo el cual el juego persistirá la tabla en `SavedVariables/<AddonName>.lua`.
> - **Prohibición de `LibStub`:** En ESO moderno `LibStub` está formalmente obsoleto. Las dependencias se declaran con `## DependsOn:` y las librerías exponen sus tablas globales directamente.

---

## 2. Ciclo de Vida e Inicialización

El punto de entrada debe aguardar a que el motor termine de cargar los archivos del addon antes de acceder a las variables guardadas o crear elementos de UI:

```lua
-- Espacio de nombres único para evitar colisiones en _G
MiAddon = MiAddon or {}
local MiAddon = MiAddon

MiAddon.name = "MiAddon"
MiAddon.version = "1.0.0"
MiAddon.variableVersion = 1

local function OnAddOnLoaded(eventCode, addOnName)
    if addOnName ~= MiAddon.name then return end
    
    -- Desregistrar de inmediato para no consumir ciclos en otros addons
    EVENT_MANAGER:UnregisterForEvent(MiAddon.name, EVENT_ADD_ON_LOADED)

    -- 1. Inicializar persistencia
    MiAddon:InitializeSavedVariables()

    -- 2. Inicializar módulos y UI
    MiAddon:Initialize()
end

EVENT_MANAGER:RegisterForEvent(MiAddon.name, EVENT_ADD_ON_LOADED, OnAddOnLoaded)
```

---

## 3. Persistencia con `SavedVariables`

Utilizar la clase `ZO_SavedVars` proporcionada por ZOS para gestión automática de perfiles, defaults y versiones:

```lua
local defaults = {
    enabled = true,
    uiPosition = { x = 100, y = 100 },
    notifications = true,
}

function MiAddon:InitializeSavedVariables()
    -- Guardado a nivel de cuenta (compartido entre todos los personajes)
    self.settings = ZO_SavedVars:NewAccountWide(
        "MiAddon_SavedVariables",  -- Nombre declarado en el .txt
        self.variableVersion,      -- Versión de estructura de datos
        nil,                       -- Namespace opcional
        defaults                   -- Tabla de valores predeterminados
    )
end
```

*Para datos específicos de personaje, utilizar `ZO_SavedVars:NewCharacterIdSettings`.*

---

## 4. Sistema de Interfaz de Usuario (UI & Controls)

### Creación de Controles
1. **Vía XML (`TopLevelControl`):** Ideal para ventanas fijas, layouts complejos y estructuras con capas de fondo.
2. **Programática (`WINDOW_MANAGER`):** Recomendada para elementos dinámicos o widgets ligeros:

```lua
local wm = WINDOW_MANAGER

local control = wm:CreateTopLevelControl("MiAddon_VentanaPrincipal")
control:SetDimensions(300, 200)
control:SetAnchor(TOPLEFT, GuiRoot, TOPLEFT, 100, 100)
control:SetClampedToScreen(true)
control:SetMovable(true)
control:SetMouseEnabled(true)

local label = wm:CreateControl("$(parent)_Titulo", control, CT_LABEL)
label:SetFont("ZoFontWinH4")
label:SetText("Mi Addon")
label:SetAnchor(TOPLEFT, control, TOPLEFT, 10, 10)
```

### Integración con Escenas (`SCENE_MANAGER`)
Para que una ventana se muestre u oculte automáticamente al abrir menús o el HUD:

```lua
-- Fragmento que oculta la UI al entrar en combate o escenas modales
local fragment = ZO_HUDFadeSceneFragment:New(control)
SCENE_MANAGER:GetScene("hud"):AddFragment(fragment)
SCENE_MANAGER:GetScene("hudui"):AddFragment(fragment)
```

---

## 5. Hooks, Eventos y Comandos de Barra

### Escuchar Eventos del Juego
```lua
-- Registrar evento con filtro para no sobrecargar el hilo principal
EVENT_MANAGER:RegisterForEvent(MiAddon.name, EVENT_PLAYER_COMBAT_STATE, function(eventCode, inCombat)
    MiAddon:OnCombatStateChanged(inCombat)
end)
```

### Interceptar Funciones del Juego (Hooks)
**Prohibido sobreescribir funciones de ZOS directamente.** Utilizar los interceptores seguros provistos por el motor:

- `ZO_PreHook([objeto], "NombreFuncion", function(...) ... end)`: Ejecuta código antes de la función original. Si retorna `true`, **aborta** la ejecución original.
- `ZO_PostHook([objeto], "NombreFuncion", function(...) ... end)`: Ejecuta código inmediatamente después de la función original sin alterar su retorno.

### Comandos de Barra (Slash Commands)
```lua
SLASH_COMMANDS["/miaddon"] = function(extraArgs)
    MiAddon:ToggleUI()
end
```

---

## 6. Integración de Menú con `LibAddonMenu-2.0` (LAM2)

Estructura canónica para añadir panel de configuración en el menú de Add-Ons de ESO:

```lua
function MiAddon:CreateSettingsMenu()
    local LAM = LibAddonMenu2
    if not LAM then return end

    local panelData = {
        type = "panel",
        name = "Mi Addon",
        displayName = "|cFFD700Mi Addon|r",
        author = "MiNombre",
        version = self.version,
        registerForRefresh = true,
    }

    local optionsTable = {
        {
            type = "checkbox",
            name = "Habilitar Addon",
            tooltip = "Activa o desactiva la funcionalidad principal.",
            getFunc = function() return self.settings.enabled end,
            setFunc = function(value) self.settings.enabled = value end,
            default = true,
        },
    }

    LAM:RegisterAddonPanel("MiAddon_SettingsPanel", panelData)
    LAM:RegisterOptionControls("MiAddon_SettingsPanel", optionsTable)
end
```

---

## 7. Reglas Críticas de Rendimiento

1. **Gestión de Memoria y Recolector de Basura (GC Spikes):**
   - Prohibido instanciar tablas temporales dentro de eventos de alta frecuencia (`EVENT_UPDATE`, bucles de render o `EVENT_COMBAT_EVENT`). Reutilizar tablas estáticas.
2. **Throttling en `EVENT_UPDATE`:**
   - Si se requiere polling o animación, verificar delta time (`GetFrameTimeSeconds()`) y actualizar en intervalos mínimos (ej. cada 100 ms), nunca en cada fotograma sin control.
3. **Localización de Strings:**
   - Registrar identificadores de texto mediante `ZO_CreateStringId("SI_MIADDON_TEXTO", "Valor")` para facilitar soporte multilingüe.
