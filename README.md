# OMEGA-PHANTOM V7.0 (Apex-Chronos Singularity)

Arquitectura cuantitativa de alta frecuencia (HFT) diseñada desde primeros principios mediante **TRIZ Avanzado** y **Control Estocástico de Microestructura** para superar el desafío de **48 horas (`10.00 USDT -> 14.00 USDT`, `+40.0%` neto)** en futuros perpetuos de **Bybit Unified Trading Account (UTA)**.

---

## 1. Los 5 Saltos Arquitectónicos sobre `TRI-BRAIN-PHANTOM V4.0 / V6.x`

1. **Semáforo Ortogonal de 2 Slots con Riesgo Cero (`omega_phantom_v7_ram.py`):**
   Elimina la parálisis del `Single-Slot Mutex` habilitando un **Slot 2** cuando la Posición 1 ya aseguró su trinquete **Break-Even positivo** (`Riesgo = $0.00 USDT`) o cuando opera en cobertura **Delta-Neutral cruzada** con $|Z_t| \ge 4.00$.
2. **Fusión Sensorial a `50 Hz` (`20 ms`) `L2` + `publicTrade` y Reloj de Volumen `VPIN` (`omega_phantom_v7_radar.py`):**
   Reduce la latencia de muestreo de `150 ms` (`6.6 Hz`) a **`20 ms` (`50 Hz`)**, combinando el desequilibrio pasivo `ML-OFI L1-L5` de Cont-Kukanov-Stoikov con el flujo Taker agresivo real.
3. **Precio de Reserva de Avellaneda-Stoikov y Partición *Dual-Layer Iceberg* (`omega_phantom_v7_sniper.py`):**
   Calcula el precio límite `PostOnly` óptimo $r(s, q, t) = s - \frac{1}{2}\gamma\sigma_{\text{BV}}^2\tau$ y divide lotes superiores a `16.50 USDT` en activos `High-Beta` en dos capas pasivas (`60% L1 + 40% L2`).
4. **Geometría Campeona CPCV+DSR (`+0.44% / 45s / -0.30%`) y Kelly Asimétrico *House-Money* (`omega_phantom_v7_config.py` / `omega_phantom_v7_gestor.py`):**
   Desacopla la fracción base de Kelly por dirección (**`60% SHORT-SNIPER` / `45% LONG`**), fija la cosecha principal en **`+0.44%`**, el *Early Stagnation Unwind* en **`45.0s`** y el Stop-Loss quirúrgico interno en **`-0.30%`**, escalando el nocional en señales **`GRADO_A_PLUS`** únicamente con el excedente ganado sobre el piso protegido de `10.00 USDT`.
5. **Libro Mayor Inmutable de Cicatrices (`SCAR-LOCK-00` a `SCAR-LOCK-13`) y Baúl Forense IA (`omega_phantom_v7_baul_ia.jsonl`):**
   Preserva el 100% de los pisos duros históricos (`LOCK_HARD`) y audita contrafactualmente cada bloqueo **+15.0 segundos después** junto con la anatomía `MFE / MAE` de cada operación.

---

## 2. Topología Inmutable de 17 Archivos Canónicos

| # | Archivo | Nivel DAG / Rol Arquitectónico |
| :--- | :--- | :--- |
| 01 | `.gitignore` | Protección de `.env`, `venv`, `.lock` y archivos `.jsonl`. |
| 02 | `README.md` | Documento Maestro Unificado (SSOT) de `OMEGA-PHANTOM V7.0`. |
| 03 | `requirements.txt` | Dependencias (`ccxt`, `aiohttp`, `groq`, `python-dotenv`, `uvloop`). |
| 04 | `omega_phantom_v7_config.py` | **Nivel 0:** Exactamente 100 constantes globales únicas (`AST_100_CONSTANTES_OK`) y motor Kelly *House-Money*. |
| 05 | `omega_phantom_v7_ram.py` | **Nivel 1:** Pizarra $\mathcal{O}(1)$ en RAM, Semáforo Ortogonal de 2 Slots y Oráculo +15s del Baúl IA. |
| 06 | `omega_phantom_v7_telegram.py` | **Nivel 2:** Notificador transaccional 1:1 libre de ruido. |
| 07 | `omega_phantom_v7_stats.py` | **Nivel 3:** Contabilidad `CAJA_NEGRA`, paridad 1:1 Bybit UTA y progreso hacia `14.00 USDT`. |
| 08 | `omega_phantom_v7_tricortex.py` | **Nivel 4:** Enjambre LPU Multi-Cloud (`Groq -> Gemini -> NVIDIA`), Anti-LUNA y Glosten-Milgrom. |
| 09 | `omega_phantom_v7_radar.py` | **Nivel 5:** Motor tensorial `50 Hz`, `H-OFI`, `Hurst`, `Lyapunov`, `Hawkes` y `SCAR-LOCK-00..13`. |
| 10 | `omega_phantom_v7_sniper.py` | **Nivel 6A:** Cotizador Avellaneda-Stoikov, *Iceberg* L1/L2, *Re-Peg* `1.8s` y `TTL=3.8s`. |
| 11 | `omega_phantom_v7_gestor.py` | **Nivel 6B:** Custodia `+0.44% / 45s / -0.30%`, `Chain-Jail` y CLI `veromega`. |
| 12 | `omega_phantom_v7_main.py` | **Nivel 7:** Orquestador asíncrono sobre `uvloop`, reconciliación UTA y cerrojo `.lock`. |
| 13 | `omega_phantom_v7_oos_twin.py` | **Nivel 8:** Calibrador Walk-Forward OOS y Simulador Gemelo Digital (`--lab`). |
| 14 | `omega_phantom_v7_install.sh` | Instalador Linux y configuración del comando `veromega`. |
| 15 | `omega_phantom_v7_test_suite.py` | Suite de certificación determinista (`18/18` pruebas unitarias e integrales). |
| 16 | `tools/omega_phantom_v7_validator.py` | Compuerta 0 de auditoría estática (`UTF-8 sin BOM / LF / AST / 100 Constantes`). |
| 17 | `omega_phantom_v7_calibracion.json` | Estado calibrado OOS para *Hot-Reload* en sub-milisegundo. |