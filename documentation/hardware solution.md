# BUGSI - Hardware-Loesung
## Autarkes Geraet zur Erkennung und Zaehlung von Insekten

**Version:** 0.7.0
**Datum:** 2026-03-13
**Status:** Entwurf

---

## 1. SYSTEMUEBERSICHT

### 1.1 Konzept

```
                     1x Sonnenpanel (50W, 12V)
                    ┌──────────────────────────┐
                    │     Solarpanel 50W        │
                    └────────────┬─────────────┘
                                 │
         Pfosten A               │                  Pfosten B
            ║      ┌───────────────────────────┐          ║
            ║      │     Elektronik-Box        │          ║
            ║      │     (IP65)                │          ║
            ║      └───────────┬───────────────┘          ║
            ║                  │                           ║
            ║    ┌─────────────┴──────────────┐           ║
            ║    │       Kamera-Box            │           ║
            ║    │  IDS uEye XLS-E (USB3)     │           ║
            ║    │  Arducam 64MP (CSI-2)      │           ║
            ║    └─────────────┬──────────────┘           ║
            ║                  │                           ║
            ║                  │  ~40cm                    ║
            ║                  │                           ║
            ║    ┌─────────────┴──────────────┐           ║
            ║    │     Kontrastschirm          │           ║
            ║    │      (60 x 60 cm)           │           ║
            ║    └────────────────────────────┘           ║
            ║                                              ║
     ═══════╩══════════════════════════════════════════════╩═══  Boden
            │                                              │
       ┌────┴──────────────────────────────────────────────┴────┐
       │              Akku-Box (am Boden)                       │
       │              12V 100Ah LiFePO4                         │
       │              (~13 kg, ~33 x 17 x 22 cm)               │
       └───────────────────────────────────────────────────────┘

       ~~~~~~~~  Zigbee-Wetterstation (IP65)  ~~~~~~~~
       ~~~~~~~~  (separat, bis 100m entfernt)  ~~~~~~~~
```

**Funktionsprinzip:**
1. IDS uEye XLS-E Event-Kamera (IMX636) laeuft dauerhaft (~1 W) und erkennt Bewegung
2. Event-Kamera meldet asynchron nur Pixel-Aenderungen (kein Bild bei Stillstand → ~0 Daten)
3. Bei erkanntem Insekten-Event: Pi 5 loest 64MP Aufnahme aus (Arducam Hawkeye)
4. Hochaufloestes Bild wird lokal auf USB-Stick gespeichert
5. Periodische Uebertragung via Sixfab LTE (Cat-4, Quectel EG25-G) direkt an eigene Cloud
6. Zigbee-Wetterstation liefert Temperatur/Feuchte drahtlos
7. Cloud-basierte KI-Klassifikation (Biene/Kaefer/Motte etc.)

### 1.2 Betriebsmodi

| Modus | Beschreibung | Stromverbrauch |
|-------|-------------|----------------|
| **Ueberwachung** | IDS XLS-E aktiv, Pi 5 auf Event-Stream wartend (Low-CPU) | ~3.5 W |
| **Erfassung** | Event erkannt → 64MP Aufnahme + Speicherung | ~7 W (kurz, ~5 Sek) |
| **Upload** | Sixfab LTE einschalten → Upload → ausschalten (periodisch) | ~5 W (kurz) |
| **Nacht/Aus** | Komplett aus, nur RTC aktiv | ~0.01 W |

---

## 2. KOMPONENTENLISTE (BOM)

### 2.1 Rechenplattform

| Komponente | Spezifikation | Stueck | Preis/Stueck | Begruendung |
|-----------|--------------|--------|-------------|-------------|
| Raspberry Pi 5 (4GB) | BCM2712, 4x A76 2.4GHz | 1 | ~87 EUR | Leistungsfaehig fuer Event-Verarbeitung + Bilderfassung; native CSI-2 fuer Arducam; 2x USB 3.0 fuer IDS-Kamera + Speicher |
| MicroSD 32GB (A2) | SanDisk Extreme | 1 | ~10 EUR | Betriebssystem (Raspberry Pi OS Lite) |
| USB-Stick 64GB (USB 3.0) | Industriequalitaet, SLC/pSLC | 1 | ~15 EUR | Datenspeicher, tauschbar |

### 2.2 Kamerasystem

| Komponente | Spezifikation | Stueck | Preis/Stueck | Begruendung |
|-----------|--------------|--------|-------------|-------------|
| **IDS uEye XLS-E (UE-39B1XLS-E)** | IMX636, 1280x720, USB3, Event-basiert | 1 | ~500 EUR (Preis auf Anfrage) | Event-basierter Trigger-Sensor via **USB 3.0**; industrielle Qualitaet; Metavision SDK |
| **S-Mount Objektiv (M12)** | ~3.6mm Brennweite, passend fuer 1/2.5" Sensor | 1 | ~15 EUR | Weitwinkel fuer 60x60cm Schirm bei ~40cm Abstand |
| Arducam 64MP Hawkeye | IMX686, Autofokus, CSI-2 | 1 | ~80 EUR | High-Res Aufnahme an **CAM1** (CSI-2) |

**Kamera-Architektur (USB3 + CSI-2):**

```
    Pi 5 USB 3.0 Port                   Pi 5 CAM1 (22-pin FPC)
           │                                    │
           │  USB 3.0 (5 Gbps)                  │  MIPI CSI-2 (2-4 Lane)
           │                                    │
    ┌──────▼──────────┐                  ┌──────▼──────────┐
    │  IDS uEye XLS-E │                  │  Arducam 64MP   │
    │  UE-39B1XLS-E   │                  │  Hawkeye        │
    │  (Event-Trigger) │                  │  (Aufnahme)     │
    │  IMX636          │                  │  9152x6944 px   │
    │  1280x720        │                  │                 │
    │  0.4-2 W         │                  │                 │
    └─────────────────┘                  └─────────────────┘
```

> **IDS uEye XLS-E nutzt USB 3.0**, Arducam 64MP nutzt CSI-2 (CAM1).
> Kein Bandbreiten-Konflikt. USB3 ist robuster als ein zweites FPC-Flachbandkabel
> fuer den Ausseneinsatz. Die Kamera wird direkt ueber USB mit Strom versorgt (bus-powered).

**IDS uEye XLS-E (UE-39B1XLS-E) - Technische Daten:**

| Parameter | Wert |
|-----------|------|
| Sensor | Sony IMX636 (Event-basiert, Sony + Prophesee) |
| Aufloesung | 1280 x 720 Pixel (0.92 MP) |
| Pixelgroesse | 4.86 x 4.86 um |
| Optisches Format | 1/2.5" |
| Dynamikumfang | >120 dB |
| Aequivalente Bildrate | >10.000 FPS |
| Leistungsaufnahme | 0.4 - 2 W (USB bus-powered) |
| Schnittstelle | USB 3.0 (5 Gbps, SuperSpeed) |
| Objektivanschluss | S-Mount (M12) |
| Abmessungen | 29 x 29 x 7 mm (Board-Level) |
| Gewicht | <30 g |
| Software | IDS peak SDK + Metavision SDK (Prophesee) |
| Betriebstemperatur | -10°C bis +60°C |

**Bezugsquelle:** IDS Imaging (ids-imaging.com), Preis auf Anfrage.
https://de.ids-imaging.com/store/ue-39b1xls-e.html

**Vorteile gegenueber Prophesee GenX320 Starter Kit:**

| | IDS uEye XLS-E (UE-39B1XLS-E) | Prophesee GenX320 Starter Kit |
|---|---|---|
| **Aufloesung** | 1280 x 720 (0.92 MP) | 320 x 320 (0.1 MP) |
| **Sensor** | Sony IMX636 (industriell) | Prophesee GenX320 |
| **Schnittstelle** | USB 3.0 (robust, lange Kabel) | MIPI CSI-2 (FPC, max ~30 cm) |
| **Formfaktor** | 29x29x7 mm Board-Level, industriell | Starter Kit / Evaluation Board |
| **Leistung** | 0.4-2 W | <50 mW |
| **Support** | IDS industrieller Support + SDK | Community / Evaluation |
| **Preis** | ~500 EUR (geschaetzt) | ~300 EUR (geschaetzt) |

> **Trade-off:** Die IDS-Kamera verbraucht mehr Strom (~1 W vs. <50 mW), bietet aber
> 9x hoehere Aufloesung, industriellen Support, robuste USB3-Anbindung und den
> bewährten IMX636-Sensor (Sony + Prophesee Kooperation). Der Mehrverbrauch ist
> durch die Einsparung auf 12V-System und den Wegfall des separaten DC-DC-Wandlers
> kompensiert.

### 2.3 Energieversorgung

| Komponente | Spezifikation | Stueck | Preis/Stueck | Begruendung |
|-----------|--------------|--------|-------------|-------------|
| **LiFePO4 Akku** | **12.8V (12V), 100Ah (1.280 Wh)** | 1 | ~220 EUR | Gute Autonomie (~18 Tage ohne Sonne); leichter als 24V; separate Bodenbox |
| Solarpanel Monokristallin | 50W, 12V, ~70x55cm | 1 | ~50 EUR | **1 Panel reicht bei 12V** (Voc ~22V fuer 12V MPPT) |
| MPPT Laderegler | Victron SmartSolar 75/15 (12V) | 1 | ~50 EUR | 12V, 75V max PV-Eingang, 15A, VE.Direct |
| **Witty Pi 5 HAT+** | RP2350 MCU, RTC, Power Mgmt, **eingebauter DC/DC 6-30V→5V/5A** | 1 | ~39 EUR | Zeitgesteuertes Ein/Ausschalten; **integrierter Step-Down** (kein separater DC-DC noetig); UPS-Funktion |
https://www.uugear.com/product/witty-pi-5/

**Warum 12V 100Ah?**
- 1.280 Wh Kapazitaet (1.024 Wh nutzbar bei 80% DoD)
- Bei 58 Wh/Tag Verbrauch: **~18 Tage ohne Sonne**
- Weit ueber der Anforderung von 5 Tagen → Betrieb ueber gesamte Saison moeglich
- Ein Panel liefert ~200 Wh/Tag (Sommer) → Akku wird taeglich nachgeladen
- **Deutlich leichter als 24V** (~13 kg statt ~21 kg) → einfacherer Transport
- **Deutlich guenstiger** (~220 EUR statt ~440 EUR)

**Witty Pi 5 HAT+ — Schluesselkomponente:**

Der Witty Pi 5 HAT+ vereint **drei Funktionen** in einem Board:
1. **DC/DC-Wandler (6-30V → 5V, bis 5A):** Nimmt 12V direkt vom Akku und versorgt den Pi 5 — kein separater Step-Down-Wandler noetig
2. **RTC (±3.8-5 ppm):** Hochpraezise Echtzeituhr fuer zeitgesteuertes Ein/Ausschalten
3. **Power-Scheduling (RP2350 MCU + 16 MB Flash):** Scheduling-Skripte laufen unabhaengig vom Pi auf dem MCU — Stromzyklen auch bei OS-Absturz gesichert

| Parameter | Wert |
|-----------|------|
| Eingang | 6-30V DC (Schraubklemme) oder 5V USB-C |
| Ausgang | 5V, bis 5A (via GPIO an Pi 5) |
| MCU | RP2350 + 16 MB Flash |
| RTC-Genauigkeit | ±3.8-5 ppm |
| RTC-Batterie | CR2032 |
| Temperatursensor | 0.0625°C Aufloesung (onboard) |
| UPS-Funktion | Dual Ideal-Diode, automatische Umschaltung |
| Betriebstemperatur | -30°C bis +80°C |
| Software | Open-Source: `wp5` CLI + `wp5d` Daemon (C, pico-sdk) |

> **Vorteil:** Witty Pi 5 HAT+ ersetzt den separaten DC-DC-Wandler (24V→5V) und den
> Witty Pi 4. Weniger Komponenten, weniger Fehlerquellen, bessere Effizienz.
> Der integrierte Temperatursensor liefert Elektronik-Box-Temperatur als Bonus-Telemetrie.

**Gewichtshinweis:**

| Eigenschaft | 12V 100Ah | Anforderung |
|-------------|-----------|-------------|
| Gewicht | ~13 kg | 15 kg (Geraetelimit) |
| Abmessungen | ~33 x 17 x 22 cm | 50x50x50 cm |

> **Der Akku ist mit ~13 kg knapp unter dem 15 kg Gesamtlimit**, wird aber trotzdem
> in einer separaten Bodenbox aufgestellt (Schwerpunkt, Stabilitaet).
> Pfostenmontierte Komponenten (Elektronik, Kameras, Schirm): ~9 kg.
> Akku-Box am Boden: ~13 kg (+ Box ~1.5 kg = ~14.5 kg).
> Verbindung ueber 1-2m Kabel mit wetterfesten Steckverbindern.

### 2.4 Energiebudget-Berechnung

**Tagesverbrauch (14h aktiv, 10h aus) — mit IDS Event-Kamera + Sixfab LTE:**

| Phase | Leistung | Dauer | Energie |
|-------|----------|-------|---------|
| Ueberwachung (Pi 5 Low-CPU + IDS XLS-E USB3) | 3.5 W | 13.5 h | 47.3 Wh |
| Erfassungen (64MP, ~50 Events/Tag a 5s) | 7.0 W | ~0.07 h | 0.5 Wh |
| Sixfab LTE Upload (GPIO16 ein → senden → aus) | 5.0 W | ~0.3 h | 1.5 Wh |
| Sixfab LTE Idle (GPIO16 HW-Cutoff) | 0 W | Rest | 0 Wh |
| Zigbee Dongle | 0.3 W | 14 h | 4.2 Wh |
| SmartShunt (Akku-Monitoring, <1 mA) | 0.005 W | 24 h | 0.1 Wh |
| Nacht (komplett aus, nur RTC) | 0.01 W | 10 h | 0.1 Wh |
| **Subtotal** | | | **53.7 Wh** |
| DC-DC Verluste (~8% bei 12V→5V via Witty Pi 5) | | | **4.3 Wh** |
| **Gesamt pro Tag** | | | **~58 Wh** |

**Autarkie-Berechnung:**

| Parameter | Wert |
|-----------|------|
| Akku-Kapazitaet (nutzbar, 80% DoD) | 1.024 Wh |
| Tagesverbrauch | 58 Wh |
| **Tage ohne Sonne** | **~18 Tage** |
| Solarertrag Sommer (1x50W, ~4h Peak Sun) | ~200 Wh/Tag |
| Solarertrag Fruehling/Herbst (~2.5h) | ~125 Wh/Tag |
| **Energiebilanz Sommer** | **+142 Wh/Tag** |
| **Energiebilanz Fruehling/Herbst** | **+67 Wh/Tag** |

> Solider Energieueberschuss mit nur einem Panel. Selbst im Fruehling/Herbst ist die
> Bilanz deutlich positiv (+67 Wh/Tag). Bei laengeren Schlechtwetterperioden bietet
> der 100Ah-Akku 18 Tage Reserve — weit ueber der 5-Tage-Anforderung.

### 2.5 Batterie-Monitoring: Victron SmartShunt

**Problem:** Der Ladezustand (SoC) eines LiFePO4-Akkus laesst sich nicht allein ueber die
Spannung bestimmen — die Spannungskurve ist im Bereich 20-80% extrem flach (~12.8-13.2V).
Ein DIY-Ansatz (INA226 + eigene Coulomb-Counting-Software) ist fragil: Kalibrierungsdrift,
Shunt-Dimensionierung, fehlende Peukert-Kompensation, kein Anti-Drift-Mechanismus.

**Loesung: Victron SmartShunt 500A/50mV** — produktionsreifer Batteriemonitor.

| Komponente | Spezifikation | Stueck | Preis/Stueck | Begruendung |
|-----------|--------------|--------|-------------|-------------|
| **Victron SmartShunt 500A/50mV** | Batteriemonitor, 500A Shunt, VE.Direct | 1 | ~108 EUR | Produktionsreifer SoC: Coulomb-Counting + Spannungs-Sync + Peukert; ±0.4% Strom, ±0.3% Spannung |
| **VE.Direct-to-USB Kabel** | FTDI USB-Serial, fuer SmartShunt → Pi | 1 | ~34 EUR | Zuverlaessige kabelgebundene Datenverbindung, 1-Sek-Intervall |
| **VE.Direct-to-USB Kabel** | FTDI USB-Serial, fuer MPPT → Pi | 1 | ~34 EUR | Solar-Daten (PV-Leistung, Ladezustand, Tagesertrag) kabelgebunden |

**Einbau im Akku-Minuspfad:**

```
  Solar ──▶ Victron MPPT 75/15 ──┐
            (VE.Direct → USB      │
             → Pi /dev/victron-mppt) │
                                   ▼
  Akku (+) ────────────────────────────── Systemlast (Witty Pi 5 HAT+ → Pi 5)

  Akku (-) ────── SmartShunt ──────────── System-GND
                  (500A/50mV)
                      │
                      │ VE.Direct (4-pin JST)
                      │
                      ▼
                  VE.Direct-to-USB Kabel
                      │
                      ▼
                  Pi 5 USB Port → /dev/ttyUSB0
```

> Der SmartShunt sitzt im **Minuspfad** des Akkus. Dadurch misst er ALLEN Strom
> (Ladung von Solar + Entladung an Last) und kann den SoC praezise berechnen.

**Messwerte (jede Sekunde via VE.Direct):**

| Messwert | VE.Direct Label | Einheit | Beschreibung |
|----------|----------------|---------|-------------|
| Akkuspannung | `V` | mV | ±0.01V, ±0.3% |
| Strom | `I` | mA | ±0.01A, ±0.4% (positiv = Entladung) |
| Leistung | `P` | W | V × I |
| **State of Charge** | **`SOC`** | **‰** | **Coulomb-Counting + Spannungs-Sync, ±0.1%** |
| Verbrauchte Ah | `CE` | mAh | Seit letzter Vollladung |
| Restlaufzeit | `TTG` | min | Geschaetzt basierend auf aktuellem Verbrauch |
| Alarm | `AR` | Code | Low-Voltage, High-Voltage, Low-SoC |

**SoC-Algorithmus (intern im SmartShunt, kein eigener Code noetig):**

```
┌─────────────────────────────────────────────────────────────┐
│              SmartShunt SoC-Berechnung (intern)              │
│                                                              │
│  1. COULOMB-COUNTING (Hauptmethode)                         │
│     - Integriert Strom ueber Zeit (Ah rein/raus)            │
│     - Peukert-Kompensation (Exponent 1.05 fuer LiFePO4)    │
│     - Ladeeffizienz-Faktor (99% fuer Lithium)               │
│                                                              │
│  2. AUTOMATISCHE DRIFT-KORREKTUR                            │
│     SoC wird auf 100% zurueckgesetzt wenn ALLE zutreffen:   │
│     - Spannung > "Charged Voltage" (z.B. 14.4V)            │
│     - Strom < "Tail Current" (z.B. 4A = 4% von 100Ah)      │
│     - Bedingung haelt > 3 Minuten an                        │
│     → Passiert taeglich bei Sonnenschein automatisch!        │
│                                                              │
│  3. HISTORISCHE ZAEHLER (H1-H18)                            │
│     - Tiefste Entladung, Anzahl Zyklen, Ah gesamt           │
│     - Max/Min Spannung, letzter Sync-Zeitpunkt              │
└─────────────────────────────────────────────────────────────┘
```

**Konfiguration (einmalig via VictronConnect App):**

| Parameter | Wert fuer 12V 100Ah LiFePO4 |
|-----------|----------------------------|
| Batteriekapazitaet | 100 Ah |
| Charged Voltage | 14.4 V |
| Tail Current | 4.0% (= 4A) |
| Charged Detection Time | 3 min |
| Peukert-Exponent | 1.05 |
| Charge Efficiency | 99% |
| Discharge Floor | 20% |

**Python-Anbindung:**

```python
# pip install vedirect
from vedirect import Vedirect

def handle_data(data):
    """Wird jede Sekunde aufgerufen mit allen SmartShunt-Werten."""
    voltage_v = int(data.get('V', 0)) / 1000.0
    current_a = int(data.get('I', 0)) / 1000.0
    soc_pct = int(data.get('SOC', 0)) / 10.0
    power_w = int(data.get('P', 0))
    ttg_min = int(data.get('TTG', -1))
    consumed_ah = int(data.get('CE', 0)) / 1000.0

    print(f"SoC: {soc_pct}%, {voltage_v}V, {current_a}A, "
          f"{power_w}W, TTG: {ttg_min}min")

    # → An Cloud senden (stuendlich via Sixfab LTE)

ve = Vedirect('/dev/ttyUSB0')  # VE.Direct-to-USB Kabel
ve.read_data_callback(handle_data)
```

**Schwellwerte und Alarme (konfigurierbar via VictronConnect):**

| Schwellwert | SoC | Aktion |
|-------------|-----|--------|
| Normal | >30% | Normalbetrieb |
| Warnung | 20% | SmartShunt Alarm-Relay; Pi sendet "LOW_BATTERY" an Cloud |
| Alarm | 10% | Pi stoppt Aufnahmen, nur noch Statusmeldungen |
| Abschaltung | ~0% | BMS trennt Last automatisch; Witty Pi 5 RTC wartet auf Solarladung |

**Telemetrie-Ausgabe (stuendlich via Sixfab LTE):**

```json
{
  "battery_v": 13.1,
  "battery_soc": 72.0,
  "current_a": -0.45,
  "power_w": 5.9,
  "consumed_ah": 28.0,
  "ttg_min": 1200,
  "days_remaining": 18
}
```

**MPPT-Daten via VE.Direct (zweites USB-Kabel):**

Der Victron SmartSolar MPPT 75/15 wird mit einem eigenen VE.Direct-to-USB Kabel
an den Pi angeschlossen → `/dev/ttyUSB1`. Stabile udev-Regeln fuer Port-Zuordnung:

```bash
# /etc/udev/rules.d/99-victron.rules
SUBSYSTEM=="tty", ATTRS{serial}=="SHUNT_SERIAL", SYMLINK+="victron-shunt"
SUBSYSTEM=="tty", ATTRS{serial}=="MPPT_SERIAL", SYMLINK+="victron-mppt"
```

| MPPT-Messwert | VE.Direct Label | Beschreibung |
|---------------|----------------|-------------|
| PV-Spannung | `VPV` | Solarpanel-Spannung (mV) |
| PV-Leistung | `PPV` | Aktuelle Solarleistung (W) |
| Ladestrom | `I` | Strom in den Akku (mA) |
| Ladezustand | `CS` | 3=Bulk, 4=Absorption, 5=Float |
| Tagesertrag | `H20` | Solarertrag heute (0.01 kWh) |
| Gestern | `H22` | Solarertrag gestern (0.01 kWh) |
| Max. Leistung heute | `H21` | Spitzenleistung heute (W) |

```python
from vedirect import Vedirect

def handle_mppt(data):
    pv_power_w = int(data.get('PPV', 0))
    charge_state = int(data.get('CS', 0))
    yield_today_wh = int(data.get('H20', 0)) * 10
    print(f"Solar: {pv_power_w}W, State: {charge_state}, Today: {yield_today_wh}Wh")

ve_mppt = Vedirect('/dev/victron-mppt')
ve_mppt.read_data_callback(handle_mppt)
```

**Entscheidung: Kabelgebunden statt Bluetooth**

Beide Victron-Geraete (SmartShunt + MPPT) haben Bluetooth (BLE), das theoretisch
die VE.Direct-Kabel ersetzen koennte. Fuer BUGSI wird bewusst auf BLE verzichtet:

| | Kabelgebunden (VE.Direct USB) | Bluetooth (BLE) |
|---|---|---|
| **Zuverlaessigkeit** | Deterministisch, 1-Sek-Takt | Verbindungsabbrueche, besonders bei Temperaturwechsel |
| **Verfuegbarkeit** | Sofort nach Boot | BLE-Scan + Pairing + Encryption Key noetig |
| **Daten bei Pi-Neustart** | Sofort verfuegbar | Reconnect-Delay (5-30 Sek) |
| **RF-Interferenz** | Keine | 2.4 GHz wie Zigbee → moegliche Stoerungen |
| **Software-Stabilitaet** | `vedirect` Library: stabil, einfach | `victron-ble`: erfordert manuell extrahierten Encryption Key; Library-Updates koennen brechen |
| **Stromverbrauch** | Kein zusaetzlicher (USB powered by Pi) | BLE-Scanning verbraucht CPU + Radio |
| **Kabelaufwand** | 2x VE.Direct USB Kabel (~68 EUR) | Kein Kabel (spart 68 EUR) |
| **Pi 5 BLE-Chip** | Nicht beansprucht | Teilt BCM43455 mit WiFi; unter Last instabil |
| **Wartbarkeit** | Kabel tauschen = trivial | Encryption Key muss bei Geraetewechsel neu extrahiert werden |

> **Fazit:** Die 68 EUR fuer zwei VE.Direct-Kabel sind gut investiert. BLE-Verbindungen
> in einem autarken Feldgeraet ohne Bedienpersonal sind ein unnoetig fragiler Punkt.
> Jeder BLE-Verbindungsabbruch erfordert Reconnect-Logik, Timeouts, Fallbacks — Code,
> der geschrieben, getestet und gewartet werden muss. Die kabelgebundene Loesung
> funktioniert ab dem ersten `open('/dev/victron-shunt')` zuverlaessig.
>
> **Bluetooth bleibt nutzbar** fuer: Vor-Ort-Diagnose mit der VictronConnect App
> auf dem Smartphone (kein Einfluss auf den Pi-Betrieb).

### 2.6 Konnektivitaet: Sixfab 4G/LTE Modem Kit (Quectel EG25-G)

| Komponente | Spezifikation | Stueck | Preis/Stueck | Begruendung |
|-----------|--------------|--------|-------------|-------------|
| **Sixfab Base HAT** | HAT fuer RPi 5, Mini PCIe Sockel, SIM-Slot, GPIO Power Control | 1 | ~45 EUR | **GPIO16 Hardware-Abschaltung (0 mA)**; Micro SIM Slot |
| **Quectel EG25-G Mini PCIe Modul** | LTE Cat-4, 150/50 Mbps, GNSS, Mini PCIe | 1 | ~55 EUR | Alle DE-Baender (B1/B3/B7/B8/B20/B28); 3G/2G Fallback |
| LTE-Antennen (MIMO) | 2x SMA Pigtail (im Kit enthalten) | 1 Set | inkl. | MIMO fuer besseren Durchsatz und Empfang |
| SIM-Karte (IoT-Tarif) | z.B. 1NCE (~10 EUR/500MB/10J) oder Telekom IoT | 1 | ~10 EUR | **Eigene SIM → provider-unabhaengig** |

**Link:** https://www.amazon.de/Raspberry-Modem-Kit-Cloud-Software-Fernbedienung-Netzwerk%C3%BCberwachung/dp/B089X8N2TY/ref=sr_1_1?__mk_de_DE=%C3%85M%C3%85%C5%BD%C3%95%C3%91&crid=1P5531WAY6E50&dib=eyJ2IjoiMSJ9._yGmVv59TbeSn4IEGjq0oyyu2Fxd-yVebB6TgeDC-RjGjHj071QN20LucGBJIEps.OkDIVanGHfM8By4zWEUutfzuAEoeVLkPYLOEsxt72eU&dib_tag=se&keywords=sixfab+4g&qid=1772717255&sprefix=sixfab+4g%2Caps%2C197&sr=8-1

**Sixfab + EG25-G - Eckdaten:**

| Parameter | Wert |
|-----------|------|
| Zellulare Technologie | LTE Cat-4 / WCDMA / GPRS |
| Frequenzbaender (DE) | LTE-FDD B1/B3/B7/B8/B12/B13/B18/B19/B20/B25/B26/B28 |
| Max. Datenrate | 150 Mbps Download / 50 Mbps Upload |
| Datenmodell | **Volle IP-Konnektivitaet** (kein Store-and-Forward-Lock-in) |
| SIM-Karte | Eigene Micro SIM (3FF), jeder Anbieter moeglich |
| Modem aus (GPIO16 HIGH) | **0 mA** (Hardware-Trennung, nicht nur Sleep) |
| Modem Sleep (AT+QSCLK=1) | ~1.8 mA (Modul) |
| Modem Idle (netzverbunden) | ~30-50 mA (HAT + Modul) |
| Sendestrom | bis ~1 A Peak |
| Schnittstelle zum Pi | USB (intern via Mini PCIe-to-USB auf dem Base HAT) |
| Linux-Interface | QMI (empfohlen), MBIM, PPP, AT Commands |
| GPS | Integriert (GPS, GLONASS, BeiDou, Galileo, QZSS) |
| Zertifizierungen | CE, FCC, RoHS |



**GPIO16 Hardware-Abschaltung (Kernfeature):**

```
   Raspberry Pi 5 GPIO16 (PWR_DSBLE_P)
          │
          │  HIGH → Modem komplett stromlos (0 mA)
          │  LOW  → Modem eingeschaltet
          ▼
   ┌──────────────────────────┐
   │   Sixfab Base HAT        │
   │   ┌────────────────────┐ │
   │   │  Quectel EG25-G    │ │
   │   │  (Mini PCIe)       │ │
   │   │  LTE Cat-4         │ │
   │   └────────────────────┘ │
   │   SIM-Slot (Micro SIM)   │
   └──────────────────────────┘
```

> **Betriebsmodus fuer BUGSI:** Das LTE-Modem ist die meiste Zeit **komplett aus** (GPIO16 HIGH, 0 mA).
> Stuendlich wird es eingeschaltet (GPIO16 LOW), sendet gesammelte Daten, und wird wieder abgeschaltet.
> Dadurch entsteht kein Idle-Verbrauch — anders als bei Always-On-Modems.

**Upload-Zyklus (stuendlich):**

```
GPIO16 LOW          Modem Boot        Netz-Registrierung    Upload           GPIO16 HIGH
    │                  │                    │                   │                  │
    ▼                  ▼                    ▼                   ▼                  ▼
    ├──── ~2 Sek ──────├──── ~15 Sek ──────├──── ~10 Sek ─────├──── ~3 Sek ─────┤
    │                  │                    │                   │                  │
    └──────────────────┴────────────────────┴───────────────────┴──────────────────┘
                              Gesamt: ~30 Sek pro Upload-Zyklus
```

**Datenvolumen-Strategie:**

| Datentyp | Pro Event | Pro Tag (50 Events) | Upload-Methode |
|----------|-----------|---------------------|----------------|
| Thumbnail (480p JPEG, Q75) | ~30 KB | ~1.5 MB | HTTPS POST |
| Event-Metadaten (JSON) | ~0.2 KB | ~10 KB | HTTPS POST |
| Umweltdaten (Zigbee) | - | ~5 KB | HTTPS POST (stuendlich) |
| Geraetestatus | - | ~5 KB | HTTPS POST (stuendlich) |
| **Upload gesamt** | | **~1.5 MB/Tag** | |
| **Pro Monat** | | **~45 MB/Monat** | |

> Rohbilder (64MP, ~8 MB/Stueck, ~400 MB/Tag) bleiben lokal auf USB-Stick.
> Nur kompakte 480p Thumbnails werden uebertragen.
> Bei Cat-4 (150 Mbps): 1.5 MB Upload dauert **< 1 Sekunde** (vs. 28 Min bei Notecard).
>
> **SIM-Empfehlung:** 1NCE IoT SIM (~10 EUR fuer 500 MB / 10 Jahre, DE/EU-Roaming).
> Alternative: Telekom IoT-Tarif, Vodafone IoT, oder jeder beliebige Mobilfunkanbieter.

**Remote-Zugriff (direkt, kein zweiter Dongle noetig):**

| Feature | Status | Umsetzung |
|---------|--------|-----------|
| SSH / Remote Shell | **Ja** | Tailscale/WireGuard direkt ueber EG25-G |
| OTA Updates fuer Pi | **Ja** | apt upgrade, scp, rsync ueber SSH |
| Remote-Konfiguration | **Ja** | SSH + Konfig-Dateien, oder HTTPS Polling |
| Remote-Neustart | **Ja** | SSH: `sudo reboot`, oder HTTPS Command |
| Transparente IP-Verbindung | **Ja** | QMI/MBIM → wwan0 Interface, volle IP |
| Echtzeit-Statusabfrage | **Ja** | SSH oder HTTPS on-demand |

**Python-Anbindung (Modem Power Control + Upload):**

```python
import RPi.GPIO as GPIO
import subprocess
import time
import httpx

MODEM_PWR_PIN = 16  # GPIO16 = Sixfab PWR_DSBLE_P
API_URL = "https://api.eigener-server.de/bugsi"

def modem_on():
    """Schaltet LTE-Modem ein (GPIO16 LOW)."""
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(MODEM_PWR_PIN, GPIO.OUT)
    GPIO.output(MODEM_PWR_PIN, GPIO.LOW)
    time.sleep(20)  # Warten auf Boot + Netz-Registrierung
    subprocess.run(['sudo', 'qmicli', '-d', '/dev/cdc-wdm0',
                    '--dms-set-operating-mode=online'], check=True)
    subprocess.run(['sudo', 'ip', 'link', 'set', 'wwan0', 'up'], check=True)

def modem_off():
    """Schaltet LTE-Modem komplett aus (GPIO16 HIGH, 0 mA)."""
    subprocess.run(['sudo', 'qmicli', '-d', '/dev/cdc-wdm0',
                    '--dms-set-operating-mode=offline'], timeout=5)
    time.sleep(2)
    GPIO.output(MODEM_PWR_PIN, GPIO.HIGH)  # Hardware-Cutoff

def upload_data(thumbnails, telemetry):
    """Modem einschalten, Daten senden, Konfig abholen, Modem ausschalten."""
    modem_on()
    try:
        with httpx.Client(base_url=API_URL, timeout=30) as client:
            # Telemetrie + Umweltdaten senden
            client.post("/telemetry", json=telemetry)
            # Thumbnails hochladen
            for img_path in thumbnails:
                with open(img_path, 'rb') as f:
                    client.post("/thumbnails", files={"image": f})
            # Remote-Konfig abholen (HTTPS Polling)
            resp = client.get("/config")
            if resp.status_code == 200:
                apply_config(resp.json())
    finally:
        modem_off()
```

> **Tailscale fuer permanenten SSH-Zugang:** Optional kann Tailscale so konfiguriert werden,
> dass es sich bei jedem Modem-Einschalten kurz verbindet. Fuer On-Demand-SSH: Modem
> per HTTPS-Befehl dauerhaft einschalten → SSH-Session → Modem wieder ausschalten.

### 2.6 Sensorik: Zigbee-Wetterstation

| Komponente | Spezifikation | Stueck | Preis/Stueck | Begruendung |
|-----------|--------------|--------|-------------|-------------|
| **SONOFF SNZB-02WD** | Temp + Feuchte, IP65, Zigbee 3.0, LCD | 1 | ~20 EUR | Outdoor-faehig (IP65), ±0.2°C, ±2% RH, Batterie (CR2450, ~1 Jahr) |
| **SONOFF ZBDongle-E** | EFR32MG21, Zigbee 3.0, USB | 1 | ~20 EUR | Zigbee-Koordinator fuer Pi 5; gut unterstuetzt (zigpy/bellows) |
| USB-Verlaengerungskabel | USB 2.0, 15-20 cm | 1 | ~3 EUR | **Pflicht:** Abstand zum Pi 5 USB 3.0 Port (2.4 GHz Interferenz) |

**Zigbee Software-Stack (direkt, ohne Zigbee2MQTT/Mosquitto):**

```
SONOFF SNZB-02WD          SONOFF ZBDongle-E            Raspberry Pi 5
 (Zigbee Sensor)            (Koordinator)
       │                        │                           │
       │  Zigbee 3.0            │  USB                      │
       │  (2.4 GHz)             │  (/dev/ttyUSB1)           │
       └────────────────────────┘                           │
                                                            │
                    ┌───────────────────────────────────────┘
                    │
        ┌───────────▼───────────┐
        │   zigpy + bellows     │    Python-Bibliothek
        │   (im bugsi-daemon)   │    (kein separater Service)
        │                       │
        │   → Direkte Zigbee-   │    Kein Node.js noetig
        │     Kommunikation     │    Kein Mosquitto noetig
        │   → Temp/Feuchte      │
        │     auslesen          │    ~100 MB RAM gespart
        └───────────────────────┘
```

> **zigpy** ist die Python-Referenz-Bibliothek fuer Zigbee (verwendet in Home Assistant).
> **bellows** ist das Backend fuer Silicon Labs EFR32-Chips (= SONOFF ZBDongle-E).
> Installation: `pip install zigpy bellows`

> **Zigbee-Reichweite im Freifeld:** 100-200 m (Sichtlinie) mit Standardantennen.
> Fuer den typischen Einsatz (Sensor am gleichen Pfosten oder wenige Meter entfernt)
> mehr als ausreichend.
>
> **Alternative fuer groessere Entfernungen:** LoRa (868 MHz, 2-15 km Reichweite).
> Jedoch teurer und komplexer. Zigbee reicht fuer den aktuellen Anwendungsfall.

### 2.7 Gehaeuse und Mechanik

| Komponente | Spezifikation | Stueck | Preis/Stueck | Begruendung |
|-----------|--------------|--------|-------------|-------------|
| IP65 Anschlusskasten (Elektronik) | ~250 x 200 x 120 mm, ABS/PC, UV-stabil | 1 | ~35 EUR | Elektronik-Gehaeuse (Pi, Sixfab HAT, Laderegler) |
| **IP65 Akku-Box (Boden)** | ~40 x 20 x 25 cm, Kunststoff, UV-stabil | 1 | ~30 EUR | Separates Gehaeuse fuer 12V 100Ah Akku am Boden |
| Kabelverschraubungen | M16/M20, IP68 | 8 | ~2 EUR | Kabel-Durchfuehrungen (beide Boxen) |
| Kamera-Gehaeuse | Kleines IP65 Gehaeuse mit Glasfenster | 1 | ~15 EUR | Schutz fuer IDS-Kamera + Arducam |
| Aluminium-Pfosten | 40x40mm, 1.5m, Vierkantrohr | 2 | ~15 EUR | Hauptstruktur |
| Querstrebe | Aluminium, 60cm | 1 | ~8 EUR | Verbindung Pfosten, Montage Elektronikbox |
| Pfostenhuelsen | Einschlag- oder Einschraub-Bodenhuelsen | 2 | ~10 EUR | Stabile Befestigung im Boden |
| Kontrastschirm | Weisses HPL oder PVC-Platte, 60x60cm, UV-stabil | 1 | ~20 EUR | Einheitlicher Hintergrund |
| Montage-Kleinteile | Schellen, Winkel, Schrauben, Edelstahl | 1 | ~15 EUR | Befestigung |
| Kabelkanal | UV-stabiler Wellschlauch | 3m | ~8 EUR | Kabelschutz (Pfosten + Boden-Akku) |
| Wetterfeste Steckverbinder | z.B. MC4 oder IP68 Rundstecker, 12V | 1 Set | ~10 EUR | Trennbare Verbindung Akku-Box ↔ Elektronik-Box |

### 2.8 Sonstiges

| Komponente | Spezifikation | Stueck | Preis/Stueck | Begruendung |
|-----------|--------------|--------|-------------|-------------|
| **USB 2.0 Hub (kompakt)** | 4-Port, passiv | 1 | ~8 EUR | Fuer 2x VE.Direct-to-USB Kabel (SmartShunt + MPPT) |
| Kabel und Stecker | Diverse (USB-C, JST, Schraubklemmen) | 1 Set | ~20 EUR | Interne Verdrahtung |
| GPIO-Kabel | Dupont-Kabel Set | 1 | ~5 EUR | Sensor-Anschluss |

**USB-Port-Belegung am Pi 5:**

| Port | Geraet | Begruendung |
|------|--------|-------------|
| USB 3.0 #1 | IDS uEye XLS-E (Event-Kamera) | Braucht USB3-Bandbreite fuer Event-Daten |
| USB 3.0 #2 | USB-Stick 64GB (Datenspeicher) | Schnelle Schreibgeschwindigkeit |
| USB 2.0 #1 | ZBDongle-E (via Verlaengerungskabel) | Zigbee, nur geringe Bandbreite |
| USB 2.0 #2 | USB 2.0 Hub → 2x VE.Direct-to-USB | SmartShunt + MPPT, je 19200 Baud |

> **Alle 4 USB-Ports des Pi 5 sind belegt.** Die zwei VE.Direct-Kabel teilen sich
> einen USB 2.0 Port ueber einen kleinen Hub (seriell, 19200 Baud → keine Bandbreitenprobleme).
> Der Sixfab Base HAT nutzt intern den Mini-PCIe-Slot (kein USB-Port belegt).

---

## 3. KOSTENAUFSTELLUNG

### 3.1 Stueckkosten Prototyp

| Kategorie | Kosten/Stueck |
|-----------|--------------|
| Rechenplattform (Pi 5 + Speicher) | 112 EUR |
| Kamerasystem (IDS XLS-E + Objektiv + 64MP) | 595 EUR |
| Energieversorgung (1x Solar + Akku 12V/100Ah + MPPT + Witty Pi 5 HAT+) | 359 EUR |
| Batterie-Monitoring (SmartShunt + 2x VE.Direct USB Kabel) | 176 EUR |
| Konnektivitaet (Sixfab Base HAT + EG25-G + SIM) | 125 EUR |
| Sensorik (Zigbee Dongle + Sensor) | 43 EUR |
| Gehaeuse und Mechanik | 166 EUR |
| Kabel und Sonstiges (inkl. USB Hub) | 33 EUR |
| **Gesamt pro Stueck** | **~1.609 EUR** |

### 3.2 Projektkosten Phase 1 (3 Prototypen)

| Position | Kosten |
|----------|--------|
| 3x Prototyp-Geraete | 4.827 EUR |
| Ersatzteile und Backup-Komponenten | 100 EUR |
| Versand | 70 EUR |
| **Gesamt Phase 1** | **~4.997 EUR** |
| **Budget** | **5.000 EUR** |
| **Reserve** | **~3 EUR** |

> **Budget wird eingehalten.** Die Umstellung auf 12V und 1 Panel spart erheblich
> gegenueber der 24V/2-Panel-Variante (~123 EUR/Stueck). Der Mehrpreis der IDS-Kamera
> gegenueber dem GenX320 (~200 EUR) wird durch die Energie-Einsparungen kompensiert.

### 3.3 Zielkosten Pilot (1.000 EUR/Stueck)

| Massnahme | Einsparung |
|-----------|-----------|
| Pi CM4 (2GB) + Custom Carrier Board (CSI + USB3) | -30 EUR |
| IDS OEM-Preis bei 10+ Stueck | -150 EUR (geschaetzt) |
| Kleinerer Akku (12V 50Ah, reicht bei Solar) | -100 EUR |
| Mengenrabatt | -50 EUR |
| EG25-G direkt auf Custom Board (kein Sixfab HAT) | -45 EUR |
| **Reduzierte Stueckkosten** | **~1.234 EUR** |

> Noch ueber 1.000 EUR Ziel. Fuer Serie: IMX636-Chip auf eigenem PCB + EG25-G on-board
> → Ziel ~500 EUR/Stueck realistisch.

---

## 4. BLOCKSCHALTBILD

```
┌──────────────────────────────────────────────────────────────────┐
│                      ELEKTRONIK-BOX (IP65, pfostenmontiert)      │
│                                                                  │
│  ┌────────────┐    ┌───────────┐    ┌─────────────────────┐     │
│  │ 1x Solar   │───▶│ Victron   │───▶│  ← 12V von         │     │
│  │ 50W        │    │ SmartSolar│    │    Akku-Box (Boden) │     │
│  │ (~22V Voc) │    │ 75/15     │    └──────────┬──────────┘     │
│  └────────────┘    └───────────┘               │ 12V            │
│                                     ┌──────────▼──────────┐     │
│                                     │  Witty Pi 5 HAT+    │     │
│                                     │  (Power Mgmt + RTC  │     │
│                                     │   + DC/DC 12V→5V)   │     │
│                                     └──────────┬──────────┘     │
│                                                │ 5V via GPIO    │
│                                     ┌──────────▼──────────┐     │
│  ┌────────────┐   USB 3.0           │                     │     │
│  │  IDS uEye  │◀───────────────────▶│                     │     │
│  │  XLS-E     │                     │   Raspberry Pi 5    │     │
│  │  Event-Cam │                     │     (4GB RAM)       │     │
│  └────────────┘                     │                     │     │
│                                     │   ┌─────┐ ┌─────┐  │     │
│  ┌────────────┐   CAM1 (CSI-2)     │   │SD   │ │USB  │  │     │
│  │  64MP      │◀───────────────────▶│   │Card │ │Stick│  │     │
│  │  Arducam   │                     │   └─────┘ └─────┘  │     │
│  └────────────┘                     │                     │     │
│                                     └──┬────┬────┬────┬──┘     │
│                                        │    │    │    │         │
│  ┌────────────┐   USB (via Hub)        │    │    │    │         │
│  │  Zigbee    │◀──────────────────────┘    │    │    │         │
│  │  ZBDongle-E│                            │    │    │         │
│  └────────────┘                            │    │    │         │
│       ▲ Zigbee 2.4GHz                     │    │    │         │
│       │                         ┌──────────▼──┐│    │         │
│  ┌────┴───────┐                 │ Sixfab Base ││    │         │
│  │ SNZB-02WD  │                 │ HAT (GPIO16)││    │         │
│  │ Temp/Hum   │                 │ + EG25-G    ││    │         │
│  │ (IP65)     │                 │ LTE Cat-4   ││    │         │
│  │ (extern)   │                 │ (Micro SIM) ││    │         │
│  └────────────┘                 └──────┬──────┘│    │         │
│                                        │       │    │         │
│                                                │    │         │
│  ┌──────────────────┐  VE.Direct (via USB Hub)  │    │         │
│  │ Victron SmartShunt│◀────────────────────────┘    │         │
│  │ 500A/50mV        │  (/dev/victron-shunt)         │         │
│  │ (im Akku-Minus)  │                               │         │
│  └──────────────────┘                               │         │
│                                          ┌──────▼────┐         │
│                                          │LTE Antenne│         │
│                                          └───────────┘         │
└──────────────────────────────────────────────────────┘         │
                                                                  │
  ┌──────────────────────┐                                       │
  │    AKKU-BOX          │  12V Kabel (wetterfeste Stecker)      │
  │    (IP65, am Boden)  │◀──────────────────────────────────────┘
  │                      │
  │  LiFePO4 12V 100Ah  │
  │  ~13 kg              │
  └──────────────────────┘

                    ┌────────────────────────────────────┐
                    │        EIGENER CLOUD SERVICE       │
                    │                                    │  LTE Cat-4
                    │  - HTTPS API (Telemetrie + Bilder) │◀──────────
                    │  - HTTPS API (Remote-Konfig)       │  (direkt)
                    │  - KI-Klassifikation (ML-Modell)   │
                    │  - Dashboard + Monitoring          │
                    │  - SSH/Tailscale (Remote-Zugriff)  │
                    └────────────────────────────────────┘
```

---

## 5. SOFTWARE-ARCHITEKTUR (UEBERSICHT)

### 5.0 Architektur-Entscheidung: Monolithisch statt MQTT

**Warum kein MQTT-Broker / Microservice-Architektur?**

Alle Komponenten laufen auf **einem einzigen Raspberry Pi 5**. Ein MQTT-Broker (Mosquitto)
mit mehreren entkoppelten systemd-Services (Zigbee2MQTT, Uploader, Config-Listener, etc.)
wuerde folgende Nachteile bringen:

- **Unnoetige Komplexitaet:** Mosquitto + Node.js (Zigbee2MQTT) + paho-mqtt fuer IPC auf einem Geraet
- **Hoeherer RAM-Verbrauch:** ~150-200 MB Overhead (Node.js allein ~80-120 MB)
- **Mehr Fehlermodi:** Broker-Absturz = alles steht (Single Point of Failure wie monolithisch, aber mit Extra-Schichten)
- **Kein echter Entkopplungsvorteil:** Wenn der Pi abstuerzt, gehen alle Services gleichzeitig runter

**Stattdessen:** Ein monolithischer Python-Prozess (`bugsi-daemon`) als einziger systemd-Service.
Direkte Funktionsaufrufe statt IPC. Zigbee direkt via `zigpy`/`bellows` (kein Node.js).
Cloud-Upload via HTTPS POST (kein MQTT-Broker noetig).

> **Spaetere Skalierung:** Falls in der Serienphase mehrere Geraete gleichzeitig
> Daten an einen zentralen Server senden, kann serverseitig ein Message-Broker
> (z.B. MQTT, RabbitMQ) eingefuehrt werden. Das betrifft nur die Cloud-Seite,
> nicht die Geraete-Software.

```
┌──────────────────────────────────────────────────────────┐
│                    Raspberry Pi 5                          │
│                                                            │
│  ┌────────────────────────────────────────────────────┐    │
│  │          bugsi-daemon (ein Python-Prozess)         │    │
│  │          systemd Service (Restart=always)          │    │
│  │                                                    │    │
│  │  ┌─────────────────────────────────────────────┐   │    │
│  │  │  Event-Erkennung (Thread)                   │   │    │
│  │  │  IDS peak + Metavision SDK (USB3)           │   │    │
│  │  │  → IDS uEye XLS-E Event-Stream              │   │    │
│  │  │  → Clustering → Trigger-Logik               │   │    │
│  │  └──────────────┬──────────────────────────────┘   │    │
│  │                 │ Trigger (direkter Funktionsaufruf)│    │
│  │  ┌──────────────▼──────────────────────────────┐   │    │
│  │  │  Bilderfassung                              │   │    │
│  │  │  Picamera2(1) → 64MP JPEG → USB-Stick      │   │    │
│  │  │  → Thumbnail (480p) → Upload-Queue          │   │    │
│  │  └─────────────────────────────────────────────┘   │    │
│  │                                                    │    │
│  │  ┌─────────────────────────────────────────────┐   │    │
│  │  │  Zigbee-Sensor (Thread)                     │   │    │
│  │  │  zigpy + bellows (direkt, kein Zigbee2MQTT) │   │    │
│  │  │  ZBDongle-E → SNZB-02WD Temp/Feuchte       │   │    │
│  │  └─────────────────────────────────────────────┘   │    │
│  │                                                    │    │
│  │  ┌─────────────────────────────────────────────┐   │    │
│  │  │  LTE-Upload (periodisch)                    │   │    │
│  │  │  GPIO16 Modem ein → HTTPS POST → Modem aus  │   │    │
│  │  │  Thumbnails + Telemetrie + Umweltdaten      │   │    │
│  │  └─────────────────────────────────────────────┘   │    │
│  │                                                    │    │
│  │  ┌─────────────────────────────────────────────┐   │    │
│  │  │  Remote-Konfig (waehrend Upload-Fenster)    │   │    │
│  │  │  HTTPS GET → Konfig-Aenderungen abholen     │   │    │
│  │  │  → Parameter anpassen / Neustart auslösen   │   │    │
│  │  └─────────────────────────────────────────────┘   │    │
│  │                                                    │    │
│  │  ┌─────────────────────────────────────────────┐   │    │
│  │  │  Health-Check + Watchdog                    │   │    │
│  │  │  Akku (SmartShunt), Speicher, Kameras, LTE  │   │    │
│  │  └─────────────────────────────────────────────┘   │    │
│  │                                                    │    │
│  └────────────────────────────────────────────────────┘    │
│                                                            │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Raspberry Pi OS Lite (64-bit)                     │    │
│  │  + Python 3 + IDS peak + Metavision SDK             │    │
│  │  + libcamera/Picamera2 (fuer Arducam 64MP)         │    │
│  │  + zigpy + bellows (Zigbee direkt)                 │    │
│  │  + httpx + qmicli (LTE Upload)                     │    │
│  └────────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────────┘
```

### 5.1 Event-basierter Erkennungsalgorithmus

```
┌──────────────┐
│  IDS uEye    │    Asynchroner Event-Stream (USB 3.0)
│  XLS-E       │    (nur bei Pixel-Aenderung)
│  1280x720    │
│  0.4-2 W     │
└──────┬───────┘
       │ Events (x, y, timestamp, polarity)
       ▼
┌──────────────┐
│  Metavision  │    Event-Clustering + Filterung
│  SDK         │    - Rausch-Events filtern (AFK)
│  Pipeline    │    - Raeumliche Cluster bilden
│              │    - Cluster-Groesse pruefen (5-60mm)
└──────┬───────┘
       │ Cluster erkannt → Insekt-Kandidat
       ▼
┌──────────────┐
│  Trigger-    │    Entscheidungslogik
│  Logik       │    - Min. Event-Anzahl im Cluster?
│              │    - Cluster-Groesse passend?
│              │    - Cooldown abgelaufen?
└──────┬───────┘
       │ JA → Trigger!
       ▼
┌──────────────┐
│  Picamera2(1)│    High-Res Aufnahme (CAM1)
│  64MP Shot   │    - Arducam Hawkeye direkt via CSI-2
│              │    - JPEG speichern auf USB-Stick
│              │    - Thumbnail (480p, ~30KB) erstellen
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Cooldown    │    Konfigurierbarer Cooldown
│  (Default:   │    - Verhindert Doppelzaehlung
│   10 Sek)    │    - Anpassbar via Remote-Konfig (HTTPS)
└──────────────┘
```

---

## 6. GEWICHTSABSCHAETZUNG

### Pfostenmontierte Komponenten

| Komponente | Gewicht |
|-----------|---------|
| Solarpanel 1x 50W | ~2.5 kg |
| Elektronikbox (Gehaeuse + Pi + Sixfab HAT + Kameras + MPPT) | ~2.0 kg |
| Kontrastschirm (PVC/HPL) | ~1.0 kg |
| Aluminium-Pfosten (2x) | ~2.0 kg |
| Querstrebe + Montage | ~1.0 kg |
| Kabel + Sonstiges | ~0.5 kg |
| **Pfosten-Gesamt** | **~9.0 kg** |

### Boden-Komponenten

| Komponente | Gewicht |
|-----------|---------|
| LiFePO4 Akku 12V 100Ah | ~13 kg |
| Akku-Box (Gehaeuse) | ~1.5 kg |
| **Boden-Gesamt** | **~14.5 kg** |

### Transport-Gesamt: ~23.5 kg (in 2 Teilen transportierbar)

---

## 7. ABMESSUNGEN

| Element | Abmessungen |
|---------|------------|
| Elektronikbox | 25 x 20 x 12 cm |
| Akku-Box | 40 x 20 x 25 cm |
| Kontrastschirm | 60 x 60 cm |
| Solarpanel (1x) | 70 x 55 x 3 cm |
| Pfosten (ueber Boden) | 40 x 40 mm, ~120 cm |
| Pfostenabstand | ~70 cm |
| Gesamthoehe (ueber Boden) | ~150 cm |

---

## 8. BESCHAFFUNGSLISTE (EINKAUF)

| Quelle | Komponenten |
|--------|------------|
| **IDS Imaging** (ids-imaging.com) | uEye XLS-E (UE-39B1XLS-E) + S-Mount Objektiv |
| **BerryBase.de** | Pi 5, Kabel |
| **Welectron.com / Amazon.de** | Arducam 64MP Hawkeye |
| **UUGear** (uugear.com) / **Adafruit** | Witty Pi 5 HAT+ |
| **Sixfab** (sixfab.com) | 4G/LTE Modem Kit (Base HAT + EG25-G + Antennen) |
| **Amazon.de** | LiFePO4 12V 100Ah (~220 EUR), SONOFF ZBDongle-E, SONOFF SNZB-02WD, USB Hub, Gehaeuse |
| **Offgridtec.com / Amazon.de** | Victron SmartSolar 75/15, Solarpanel |
| **Offgridtec.com / SVB24.com** | Victron SmartShunt 500A/50mV, VE.Direct-to-USB Kabel |
| **Reichelt.de / Conrad.de** | Kabelverschraubungen, Klemmen, Kleinteile |
| **Baumarkt** | Alu-Pfosten, Bodenhuelsen, PVC-Platte, Montagematerial |

---

## 9. RISIKEN UND MASSNAHMEN

| Risiko | Wahrsch. | Auswirkung | Massnahme |
|--------|----------|------------|-----------|
| IDS Kamera nicht lieferbar / zu teuer | Niedrig | Hoch | Fallback: IDS uEye XCP-E (gehauste Variante) oder Prophesee GenX320 Starter Kit (CSI-2, ~300 EUR) |
| Sixfab Modem-Boot zu langsam (>30 Sek) | Niedrig | Niedrig | Upload-Intervall vergroessern; Modem laenger eingeschaltet lassen |
| LTE-Empfang im Feld schlecht | Mittel | Mittel | Externe SMA-Antenne mit Verlaengerung; SIM-Karte eines anderen Anbieters testen |
| SIM-Datenvolumen aufgebraucht | Niedrig | Mittel | 1NCE 500MB reicht ~11 Monate; Monitoring via Telemetrie; Thumbnails nur bei Bedarf |
| Zigbee-Interferenz mit Pi 5 USB 3.0 | Mittel | Niedrig | USB-Verlaengerungskabel (15-20cm) als Abstandshalter |
| USB-Port-Engpass (4 Ports, 5 Geraete) | Niedrig | Niedrig | USB 2.0 Hub fuer VE.Direct-Kabel; bei Bedarf powered Hub |
| Kondenswasser in Kamerabox | Mittel | Hoch | Silica-Gel; Membranfilter-Belueftung |
| USB-Stick Korruption | Niedrig | Hoch | ext4 Journaling; Write-Ahead-Log; regelmaessige fsck |

---

## 10. EMPFOHLENE NAECHSTE SCHRITTE

1. **Sofort:** IDS uEye XLS-E (UE-39B1XLS-E) bei IDS Imaging anfragen (Preis + Lieferzeit + SDK-Zugang)
2. **Sofort:** Sixfab 4G/LTE Modem Kit bestellen (sixfab.com) + IoT SIM-Karte (z.B. 1NCE)
3. **Sofort:** Witty Pi 5 HAT+ bestellen (uugear.com oder Adafruit)
4. **Parallel:** Pi 5, Arducam 64MP, SONOFF Zigbee-Komponenten bestellen
5. **Woche 1-2:** Laborprototyp am Tisch:
   - Pi 5 + IDS XLS-E (USB3) + 64MP Arducam (CSI-2) gleichzeitig testen
   - IDS peak SDK + Metavision SDK installieren und Event-Stream verifizieren
   - Witty Pi 5 HAT+ mit 12V-Quelle testen (Power-Scheduling, RTC)
   - Sixfab HAT: GPIO16 Power Control, QMI-Anbindung, HTTPS Upload testen
   - Tailscale/SSH ueber Sixfab LTE testen
   - zigpy/bellows + SNZB-02WD: Sensor-Datenempfang testen (direkt, ohne Zigbee2MQTT)
6. **Woche 2-3:** Trigger-Logik: Event-Clustering → 64MP Aufnahme → Thumbnail → LTE Upload
7. **Woche 3-4:** Remote-Konfiguration via HTTPS Polling, OTA-Update-Mechanismus
8. **Woche 4-5:** Gehaeusebau, 12V Stromversorgung integrieren, Feldtest
9. **Woche 5-8:** Iteration, 2 weitere Prototypen

> **Kritischer Pfad:** IDS uEye XLS-E Verfuegbarkeit und SDK-Kompatibilitaet mit Pi 5.
> Parallel-Strategie: Prototyp 1 kann mit OpenCV Frame-Diff starten (ohne Event-Kamera),
> IDS-Kamera als Upgrade sobald verfuegbar.

---

## 11. EVOLUTIONSPFAD (PROTOTYP → PILOT → SERIE)

| Phase | Plattform | Trigger | Aufnahme | Akku | Konnektivitaet | Stueckkosten |
|-------|-----------|---------|----------|------|----------------|-------------|
| **Prototyp** | Pi 5 (USB3 + CSI) | IDS XLS-E (IMX636) | 64MP Arducam | 12V 100Ah | Sixfab EG25-G | ~1.609 EUR |
| **Pilot** | CM4 + Custom Board | IDS XLS-E | 12MP Pi Cam 3 | 12V 50Ah | EG25-G direkt | ~1.234 EUR |
| **Serie** | Custom SoM | IMX636 on-board | OEM 12MP | 12V 30Ah | Quectel EG25-G OEM | ~500 EUR (Ziel) |

---

## 12. AENDERUNGSHISTORIE

| Version | Datum | Aenderungen |
|---------|-------|-------------|
| 0.1.0 | 2026-03-04 | Erstversion: Frame-basiert, 12V 40Ah, Waveshare LTE |
| 0.2.0 | 2026-03-04 | Prophesee GenX320 Event-Kamera, 12V 30Ah, CSI-2 Multiplexer |
| 0.3.0 | 2026-03-04 | Dual-CSI (kein Multiplexer), 24V 100Ah, Blues Notecard, Zigbee-Wetterstation |
| 0.3.1 | 2026-03-04 | USB-Bodenkamera entfernt (nur Kontrastschirm-Erfassung) |
| 0.3.2 | 2026-03-04 | Batterie-Monitoring: INA219→INA226 (26V→36V), Verdrahtung, SoC-Algorithmus, Shunt-Dimensionierung, Schwellwerte |
| 0.4.0 | 2026-03-04 | INA226 ersetzt durch Victron SmartShunt 500A/50mV (produktionsreifer SoC); VE.Direct-to-USB Anbindung |
| 0.4.1 | 2026-03-05 | Bluetooth vermieden: MPPT via zweites VE.Direct-USB-Kabel statt BLE; Wired-vs-BLE Vergleich |
| 0.5.0 | 2026-03-05 | Blues Notecard ersetzt durch Sixfab 4G/LTE Kit (Quectel EG25-G); eigene SIM; GPIO16 HW-Abschaltung (0 mA); volle IP (SSH/Tailscale direkt); kein zweiter LTE-Dongle noetig; Kosten 1.732 EUR/Stueck |
| 0.6.0 | 2026-03-05 | Monolithische Architektur: MQTT/Mosquitto/Zigbee2MQTT/Node.js entfernt; ein Python-Prozess (bugsi-daemon); Zigbee direkt via zigpy/bellows; Cloud-Upload via HTTPS statt MQTT; ~150 MB RAM gespart; weniger Fehlermodi |
| **0.7.0** | **2026-03-13** | **12V-System: LiFePO4 12V 100Ah statt 24V (leichter, guenstiger); IDS uEye XLS-E (IMX636, USB3) statt GenX320 (hoehere Aufloesung, industriell); Witty Pi 5 HAT+ mit integriertem DC/DC (kein separater Step-Down); 1x Solarpanel statt 2x; MPPT 75/15 statt 100/20; USB-Port-Belegung dokumentiert; Stueckkosten ~1.609 EUR (Budget eingehalten)** |
