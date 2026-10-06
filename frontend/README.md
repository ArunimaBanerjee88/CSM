# Quantum City – Unity Frontend

## Project Identity
- **Engine**: Unity 6 (6000.0.x LTS)
- **Render Pipeline**: Universal Render Pipeline (URP 17)
- **Target FPS**: 30–60 FPS on a laptop with 16 GB RAM and low-end GPU
- **Visual style**: Stylized futuristic low-poly digital-twin (not photorealistic)

---

## Quick Start

### Prerequisites
| Tool | Version |
|------|---------|
| Unity Hub | 3.x+ |
| Unity Editor | 6000.0.x (Unity 6 LTS) |
| .NET / C# | Comes with Unity |

### Opening the Project
1. Open **Unity Hub**
2. Click **Add project from disk**
3. Navigate to `CSM_V1/frontend/`
4. Select the folder and click **Open**
5. Unity will import all packages automatically (first import ~3–5 min)
6. Once imported, open **Assets → Scenes → `MainCity.unity`**
7. Press **▶ Play** — the scene should run at 30 FPS with no Console errors

---

## Scene Hierarchy: MainCity

```
MainCity
├── GameManager          ← Singleton, enforces 30 FPS + quality settings
├── DirectionalLight     ← Cool-white directional (50°/−30°), hard shadows only
├── MainCamera           ← Orbit/pan/zoom controller (RMB drag, WASD, scroll)
├── Ground               ← 150×150 flat cube, navy-blue material, static
├── CityRoot             ← CityGridBuilder: 10×10 block grid, cyan line overlay
└── Canvas_Dashboard     ← Screen-space HUD with FPS counter + metric stubs
```

---

## Folder Structure

```
frontend/
├── Assets/
│   ├── Materials/
│   │   ├── City/           Mat_CityBlock.mat  (GPU-instanced, teal-blue)
│   │   │                   Mat_GridLine.mat   (semi-transparent cyan, emissive)
│   │   └── Ground/         Mat_Ground.mat     (dark navy, near-zero roughness)
│   ├── Prefabs/
│   │   ├── City/           (future building prefabs go here)
│   │   └── UI/             (future panel prefabs go here)
│   ├── Scenes/
│   │   └── MainCity.unity  ← Primary scene
│   ├── Scripts/
│   │   ├── Core/           GameManager.cs · CameraController.cs · SceneValidator.cs
│   │   ├── City/           CityGridBuilder.cs
│   │   └── UI/             DashboardController.cs
│   ├── Settings/           URP pipeline + renderer assets
│   └── UI/
│       ├── Fonts/          (drop TMP font assets here)
│       └── Icons/          (drop icon textures here)
├── Packages/
│   └── manifest.json       ← URP 17, TMP, Input System
└── ProjectSettings/
    ├── ProjectSettings.asset
    ├── QualitySettings.asset   ← Single "QuantumCity_Low" tier
    ├── GraphicsSettings.asset  ← URP pipeline reference
    ├── TagManager.asset        ← Custom layers: CityGrid=8, Ground=9, HUD=10
    └── EditorBuildSettings.asset ← MainCity registered as Scene 0
```

---

## Performance Budget (Low-End GPU Target)

| Setting | Value | Reason |
|---------|-------|--------|
| Target FPS | 30 (soft cap) | Stable over 60 FPS chase |
| MSAA | Off | Biggest single GPU saving |
| Shadow type | Hard only | Halves shadow cost vs soft |
| Shadow distance | 80 u | Avoids offscreen cascade waste |
| Shadow cascades | 1 | One cascade is sufficient for top-down view |
| Pixel lights | 1 | Directional only, no add lights |
| Additional light shadows | Off | Saves shadow-map memory |
| Reflection probes | Off | No real-time reflections |
| LOD bias | 0.7 | Switches to lower LOD sooner |
| Block marker colliders | Removed | Zero physics cost |
| LineRenderer shadows | Off | Grid lines don't cast shadows |

---

## Camera Controls

| Input | Action |
|-------|--------|
| Right-mouse drag / Middle-mouse drag | Orbit |
| WASD / Arrow keys | Pan focus point |
| Scroll wheel | Zoom in/out |

---

## Dashboard UI Stubs (DashboardController)

These public methods are ready for future API/simulation wiring:

```csharp
dashboardController.SetCityName("Quantum City");
dashboardController.SetSimStatus("RUNNING");
dashboardController.SetTrafficFlow(72.5f);   // %
dashboardController.SetEnergy(340.2f);       // MW
dashboardController.SetPopulation(125000);
```

---

## Scene Validation

`SceneValidator.cs` runs on Awake and prints ✅/❌ Console messages for:
- MainCamera present
- Directional Light present
- CityGridBuilder present
- Canvas/Dashboard present
- GameManager singleton active

No errors on a clean scene = scene is ready to extend.

---

## What Is NOT Built Yet (By Design)

- API / backend integration
- Traffic simulation visualization
- AI agent overlays
- Quantum circuit visualization
- Detailed building assets / LOD meshes
- Particle effects / post-processing

These are intentionally deferred to keep the foundation lean and verified stable.

---

## Next Steps

1. **Wire Dashboard**: Assign TMP Text references in `Canvas_Dashboard → DashboardController` Inspector
2. **Assign Materials**: Drag `Mat_CityBlock` / `Mat_GridLine` / `Mat_Ground` into scene object slots
3. **Assign URP Asset**: In `Edit → Project Settings → Graphics`, set Scriptable Render Pipeline to `QuantumCity_URP_Asset`
4. **Enable TMP**: On first run Unity will prompt to import TMP Essentials — click **Import**
5. **Future**: Add API Manager, Traffic Visualizer, and Quantum Overlay as separate scripts/assemblies

---

*Generated for Quantum City CSM_V1 — Frontend Foundation Sprint*
