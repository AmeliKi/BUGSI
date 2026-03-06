# BUGSY - Hardware-Loesung
## Autarkes Geraet zur Erkennung und Zaehlung von Insekten

**Version:** 0.6.0
**Datum:** 2026-03-05
**Status:** Entwurf

---

## 1. SYSTEMUEBERSICHT

### 1.1 Konzept

```
                  2x Sonnenpanel (je 50W, in Serie → 24V)
                 ┌──────────────────┐ ┌──────────────────┐
                 │     Panel 1      │ │     Panel 2      │
                 └────────┬─────────┘ └────────┬─────────┘
                          │ (in Serie)          │
                          └──────────┬──────────┘
                                     │
          Pfosten A                  │                  Pfosten B
             ║      ┌───────────────────────────┐          ║
             ║      │     Elektronik-Box        │          ║
             ║      │     (IP65)                │          ║
             ║      └───────────┬───────────────┘          ║
             ║                  │                           ║
             ║    ┌─────────────┴──────────────┐           ║
             ║    │       Kamera-Box            │           ║
             ║    │  CAM0: GenX320 Event-Cam    │           ║
             ║    │  CAM1: Arducam 64MP         │           ║
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
        │              24V 100Ah LiFePO4                         │
        │              (~20 kg, ~53 x 21 x 22 cm)               │
        └───────────────────────────────────────────────────────┘

        ~~~~~~~~  Zigbee-Wetterstation (IP65)  ~~~~~~~~
        ~~~~~~~~  (separat, bis 100m entfernt)  ~~~~~~~~
```

**Funktionsprinzip:**
1. Prophesee GenX320 Event-Kamera laeuft dauerhaft (<50 mW) und erkennt Bewegung
2. Event-Kamera meldet asynchron nur Pixel-Aenderungen (kein Bild bei Stillstand → ~0 Daten)
3. Bei erkanntem Insekten-Event: Pi 5 loest 64MP Aufnahme aus (Arducam Hawkeye)
4. Hochaufloestes Bild wird lokal auf USB-Stick gespeichert
5. Periodische Uebertragung via Sixfab LTE (Cat-4, Quectel EG25-G) direkt an eigene Cloud
6. Zigbee-Wetterstation liefert Temperatur/Feuchte drahtlos
7. Cloud-basierte KI-Klassifikation (Biene/Kaefer/Motte etc.)

### 1.2 Betriebsmodi

| Modus | Beschreibung | Stromverbrauch |
|-------|-------------|----------------|
| **Ueberwachung** | GenX320 aktiv, Pi 5 auf Event-Stream wartend (Low-CPU) | ~3.0 W |
| **Erfassung** | Event erkannt → 64MP Aufnahme + Speicherung | ~7 W (kurz, ~5 Sek) |
| **Upload** | Sixfab LTE einschalten → Upload → ausschalten (periodisch) | ~5 W (kurz) |
| **Nacht/Aus** | Komplett aus, nur RTC aktiv | ~0.01 W |

---

## 2. KOMPONENTENLISTE (BOM)

### 2.1 Rechenplattform

| Komponente | Spezifikation | Stueck | Preis/Stueck | Begruendung |
|-----------|--------------|--------|-------------|-------------|
| Raspberry Pi 5 (4GB) | BCM2712, 4x A76 2.4GHz | 1 | ~87 EUR | Einzige offiziell unterstuetzte Plattform fuer GenX320 Starter Kit; **2x native CSI-2 Ports** |
| MicroSD 32GB (A2) | SanDisk Extreme | 1 | ~10 EUR | Betriebssystem (Raspberry Pi OS Lite) |
| USB-Stick 64GB (USB 3.0) | Industriequalitaet, SLC/pSLC | 1 | ~15 EUR | Datenspeicher, tauschbar |

### 2.2 Kamerasystem

| Komponente | Spezifikation | Stueck | Preis/Stueck | Begruendung |
|-----------|--------------|--------|-------------|-------------|
| **Prophesee GenX320 Starter Kit (RPi 5)** | 320x320, MIPI CSI-2, >140 dB, <50 mW | 1 | ~300 EUR (geschaetzt) | Event-basierter Trigger-Sensor an **CAM0** |
| Arducam 64MP Hawkeye | IMX686, Autofokus, CSI-2 | 1 | ~80 EUR | High-Res Aufnahme an **CAM1** |

**Kamera-Architektur (Dual-CSI-2, kein Multiplexer noetig):**

```
    Pi 5 CAM0 (22-pin FPC)          Pi 5 CAM1 (22-pin FPC)
           │                                │
           │  MIPI CSI-2 (1-Lane)           │  MIPI CSI-2 (2-4 Lane)
           │                                │
    ┌──────▼──────┐                  ┌──────▼──────────┐
    │  GenX320    │                  │  Arducam 64MP   │
    │  Event-Cam  │                  │  Hawkeye        │
    │  (Trigger)  │                  │  (Aufnahme)     │
    │  <50 mW     │                  │  9152x6944 px   │
    └─────────────┘                  └─────────────────┘
```

> **Pi 5 hat 2 unabhaengige MIPI CSI-2 Ports** (CAM0 + CAM1), jeweils 4-Lane faehig.
> Beide Kameras koennen gleichzeitig betrieben werden — kein Multiplexer noetig.
> GenX320 nutzt nur 1 Lane, Arducam 64MP nutzt 2-4 Lanes → kein Bandbreiten-Konflikt.
> Einsparung: ~57 EUR (Arducam Multi-Camera Adapter entfaellt).

**Prophesee GenX320 - Technische Daten:**

| Parameter | Wert |
|-----------|------|
| Aufloesung | 320 x 320 Pixel |
| Pixelgroesse | 6.3 x 6.3 um |
| Optisches Format | 1/5" |
| Dynamikumfang | >140 dB |
| Low-Light Cutoff | 0.05 Lux |
| Pixel-Latenz (1k Lux) | <150 us |
| Aequivalente Bildrate | ~10.000 FPS |
| Leistungsaufnahme (Sleep) | 36 uW |
| Leistungsaufnahme (Aktiv) | ~3 mW (Sensor), <50 mW (Modul) |
| Schnittstelle | MIPI CSI-2 (1-Lane D-PHY) |
| Software | OpenEB (Open Source, Apache 2.0) + V4L2 Treiber |

**Bezugsquelle:** Prophesee Webshop (prophesee.ai), Preis auf Anfrage.

### 2.3 Energieversorgung

| Komponente | Spezifikation | Stueck | Preis/Stueck | Begruendung |
|-----------|--------------|--------|-------------|-------------|
| **LiFePO4 Akku** | **25.6V (24V), 100Ah (2.560 Wh)** | 1 | ~440 EUR | Massive Autonomie (~36 Tage ohne Sonne); separate Bodenbox |
| Solarpanel Monokristallin | 50W, 12V, ~70x55cm | 2 | ~50 EUR | **2 Panels in Serie → ~44V Voc** fuer 24V MPPT |
| MPPT Laderegler | Victron SmartSolar 100/20 (24V) | 1 | ~61 EUR | 24V-faehig, 100V max PV-Eingang, 20A, VE.Direct |
| DC-DC Wandler | 24V auf 5V, 5A, Step-Down, USB-C | 1 | ~15 EUR | Stabile 5V/5A fuer Pi 5 (Eingangsbereich 10-36V) |
| Witty Pi 4 Mini | RTC + Power Management | 1 | ~30 EUR | Zeitgesteuertes Ein/Ausschalten, Auto-Restart |

**Warum 24V 100Ah?**
- 2.560 Wh Kapazitaet (2.048 Wh nutzbar bei 80% DoD)
- Bei 53 Wh/Tag Verbrauch: **~39 Tage ohne Sonne**
- Weit ueber der Anforderung von 5 Tagen → Betrieb ueber gesamte Saison ohne Akkuwechsel
- Zwei Panels in Serie liefern ~320 Wh/Tag (Sommer) → Akku wird schnell nachgeladen

**Gewichtshinweis:**

| Eigenschaft | 24V 100Ah | Anforderung |
|-------------|-----------|-------------|
| Gewicht | ~20-22 kg | 15 kg (Geraetelimit) |
| Abmessungen | ~53 x 21 x 22 cm | 50x50x50 cm |

> **Der Akku ueberschreitet das 15 kg Gesamtlimit.** Loesung: Akku wird in einer
> separaten wetterfesten Box am Boden aufgestellt (nicht pfostenmontiert).
> Pfostenmontierte Komponenten (Elektronik, Kameras, Schirm): ~10 kg.
> Akku-Box am Boden: ~22 kg (+ Box ~2 kg = ~24 kg).
> Verbindung ueber 1-2m Kabel mit wetterfesten Steckverbindern.

### 2.4 Energiebudget-Berechnung

**Tagesverbrauch (14h aktiv, 10h aus) — mit Prophesee Event-Kamera + Sixfab LTE:**

| Phase | Leistung | Dauer | Energie |
|-------|----------|-------|---------|
| Ueberwachung (Pi 5 Low-CPU + GenX320) | 3.0 W | 13.5 h | 40.5 Wh |
| Erfassungen (64MP, ~50 Events/Tag a 5s) | 7.0 W | ~0.07 h | 0.5 Wh |
| Sixfab LTE Upload (GPIO16 ein → senden → aus) | 5.0 W | ~0.3 h | 1.5 Wh |
| Sixfab LTE Idle (GPIO16 HW-Cutoff) | 0 W | Rest | 0 Wh |
| Zigbee Dongle | 0.3 W | 14 h | 4.2 Wh |
| SmartShunt (Akku-Monitoring, <1 mA) | 0.005 W | 24 h | 0.1 Wh |
| Nacht (komplett aus, nur RTC) | 0.01 W | 10 h | 0.1 Wh |
| **Subtotal** | | | **47.0 Wh** |
| DC-DC Verluste (~12% bei 24V→5V) | | | **5.6 Wh** |
| **Gesamt pro Tag** | | | **~53 Wh** |

**Autarkie-Berechnung:**

| Parameter | Wert |
|-----------|------|
| Akku-Kapazitaet (nutzbar, 80% DoD) | 2.048 Wh |
| Tagesverbrauch | 53 Wh |
| **Tage ohne Sonne** | **~39 Tage** |
| Solarertrag Sommer (2x50W, ~4h Peak Sun) | ~320 Wh/Tag |
| Solarertrag Fruehling/Herbst (~2.5h) | ~200 Wh/Tag |
| **Energiebilanz Sommer** | **+267 Wh/Tag** |
| **Energiebilanz Fruehling/Herbst** | **+147 Wh/Tag** |

> Massiver Energieueberschuss. Optionen:
> - Nur 1 Solarpanel verwenden (reicht im Sommer aus, spart 50 EUR + 2.5 kg)
> - Zweites Panel als Reserve fuer bewoelkte Perioden im Fruehling/Herbst
> - Akku-Kapazitaet ermoeglicht Betrieb ueber gesamte Saison (Maerz-Oktober)
>   auch bei laengeren Schlechtwetterperioden

### 2.5 Batterie-Monitoring: Victron SmartShunt

**Problem:** Der Ladezustand (SoC) eines LiFePO4-Akkus laesst sich nicht allein ueber die
Spannung bestimmen — die Spannungskurve ist im Bereich 20-80% extrem flach (~25.4-26.4V).
Ein DIY-Ansatz (INA226 + eigene Coulomb-Counting-Software) ist fragil: Kalibrierungsdrift,
Shunt-Dimensionierung, fehlende Peukert-Kompensation, kein Anti-Drift-Mechanismus.

**Loesung: Victron SmartShunt 500A/50mV** — produktionsreifer Batteriemonitor.

| Komponente | Spezifikation | Stueck | Preis/Stueck | Begruendung |
|-----------|--------------|--------|-------------|-------------|
| **Victron SmartShunt 500A/50mV** | Batteriemonitor, 500A Shunt, VE.Direct | 1 | ~108 EUR | Produktionsreifer SoC: Coulomb-Counting + Spannungs-Sync + Peukert; ±0.4% Strom, ±0.3% Spannung |
| **VE.Direct-to-USB Kabel** | FTDI USB-Serial, fuer SmartShunt → Pi | 1 | ~34 EUR | Zuverlaessige kabelgebundene Datenverbindung, 1-Sek-Intervall |
| **VE.Direct-to-USB Kabel** | FTDI USB-Serial, fuer MPPT → Pi | 1 | ~34 EUR | Solar-Daten (PV-Leistung, Ladezustand, Tagesertrag) kabelgebunden |

> Der SmartShunt **ersetzt den INA226 komplett** und ist in jeder Hinsicht ueberlegen:
> kalibriert ab Werk, integrierter 500A-Shunt, automatische Drift-Korrektur,
> historische Zaehler, VictronConnect App, kein eigener Code fuer SoC noetig.

**Einbau im Akku-Minuspfad:**

```
  Solar ──▶ Victron MPPT 100/20 ──┐
            (VE.Direct → USB      │
             → Pi /dev/victron-mppt) │
                                   ▼
  Akku (+) ────────────────────────────── Systemlast (DC-DC → Pi 5)

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
│     - Spannung > "Charged Voltage" (z.B. 28.8V)            │
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

| Parameter | Wert fuer 24V 100Ah LiFePO4 |
|-----------|----------------------------|
| Batteriekapazitaet | 100 Ah |
| Charged Voltage | 28.8 V |
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
| Abschaltung | ~0% | BMS trennt Last automatisch; Witty Pi RTC wartet auf Solarladung |

**Telemetrie-Ausgabe (stuendlich via Sixfab LTE):**

```json
{
  "battery_v": 26.1,
  "battery_soc": 52.0,
  "current_a": -0.32,
  "power_w": 8.35,
  "consumed_ah": 48.0,
  "ttg_min": 2280,
  "days_remaining": 38
}
```

**MPPT-Daten via VE.Direct (zweites USB-Kabel):**

Der Victron SmartSolar MPPT 100/20 wird mit einem eigenen VE.Direct-to-USB Kabel
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
die VE.Direct-Kabel ersetzen koennte. Fuer BUGSY wird bewusst auf BLE verzichtet:

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

> **Betriebsmodus fuer BUGSY:** Das LTE-Modem ist die meiste Zeit **komplett aus** (GPIO16 HIGH, 0 mA).
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
API_URL = "https://api.eigener-server.de/bugsy"

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
        │   (im bugsy-daemon)   │    (kein separater Service)
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
| **IP65 Akku-Box (Boden)** | ~60 x 25 x 25 cm, Kunststoff, UV-stabil | 1 | ~40 EUR | Separates Gehaeuse fuer 24V 100Ah Akku am Boden |
| Kabelverschraubungen | M16/M20, IP68 | 8 | ~2 EUR | Kabel-Durchfuehrungen (beide Boxen) |
| Kamera-Gehaeuse | Kleines IP65 Gehaeuse mit Glasfenster | 1 | ~15 EUR | Schutz fuer beide CSI-Kameras |
| Aluminium-Pfosten | 40x40mm, 1.5m, Vierkantrohr | 2 | ~15 EUR | Hauptstruktur |
| Querstrebe | Aluminium, 60cm | 1 | ~8 EUR | Verbindung Pfosten, Montage Elektronikbox |
| Pfostenhuelsen | Einschlag- oder Einschraub-Bodenhuelsen | 2 | ~10 EUR | Stabile Befestigung im Boden |
| Kontrastschirm | Weisses HPL oder PVC-Platte, 60x60cm, UV-stabil | 1 | ~20 EUR | Einheitlicher Hintergrund |
| Montage-Kleinteile | Schellen, Winkel, Schrauben, Edelstahl | 1 | ~15 EUR | Befestigung |
| Kabelkanal | UV-stabiler Wellschlauch | 3m | ~8 EUR | Kabelschutz (Pfosten + Boden-Akku) |
| Wetterfeste Steckverbinder | z.B. MC4 oder IP68 Rundstecker, 24V | 1 Set | ~10 EUR | Trennbare Verbindung Akku-Box ↔ Elektronik-Box |

### 2.8 Sonstiges

| Komponente | Spezifikation | Stueck | Preis/Stueck | Begruendung |
|-----------|--------------|--------|-------------|-------------|
| Kabel und Stecker | Diverse (USB-C, JST, Schraubklemmen) | 1 Set | ~20 EUR | Interne Verdrahtung |
| USB-C Kabel (kurz, gewinkelt) | 15cm | 1 | ~5 EUR | DC-DC Wandler zu Pi |
| GPIO-Kabel | Dupont-Kabel Set | 1 | ~5 EUR | Sensor-Anschluss |

---

## 3. KOSTENAUFSTELLUNG

### 3.1 Stueckkosten Prototyp

| Kategorie | Kosten/Stueck |
|-----------|--------------|
| Rechenplattform (Pi 5 + Speicher) | 112 EUR |
| Kamerasystem (GenX320 + 64MP) | 380 EUR |
| Energieversorgung (2x Solar + Akku 24V/100Ah + MPPT + DC-DC + Witty Pi) | 696 EUR |
| Batterie-Monitoring (SmartShunt + 2x VE.Direct USB Kabel) | 176 EUR |
| Konnektivitaet (Sixfab Base HAT + EG25-G + SIM) | 125 EUR |
| Sensorik (Zigbee Dongle + Sensor) | 43 EUR |
| Gehaeuse und Mechanik | 176 EUR |
| Kabel und Sonstiges | 30 EUR |
| **Gesamt pro Stueck** | **~1.732 EUR** |

### 3.2 Projektkosten Phase 1 (3 Prototypen)

| Position | Kosten |
|----------|--------|
| 3x Prototyp-Geraete | 5.196 EUR |
| Ersatzteile und Backup-Komponenten | 150 EUR |
| Versand | 80 EUR |
| **Gesamt Phase 1** | **~5.426 EUR** |
| **Budget** | **5.000 EUR** |
| **Ueberschreitung** | **~426 EUR** |

> **Budget wird um ~426 EUR ueberschritten.** Massnahmen zur Einhaltung:
> - 1 statt 2 Solarpanels pro Geraet (im Sommer ausreichend): **-150 EUR** (3x = -450 EUR)
> - Guenstigeres Akku-Modell (Timeusb statt LiTime): **-30 EUR** (3x = -90 EUR)
> - SmartShunt nur fuer Prototyp 1, Prototypen 2+3 nutzen BMS-UART: **-216 EUR**
> - **Empfehlung:** 1 Panel pro Geraet reicht im Sommer → Budget passt (-450 EUR, noch 24 EUR Reserve)

### 3.3 Zielkosten Pilot (1.000 EUR/Stueck)

| Massnahme | Einsparung |
|-----------|-----------|
| Pi CM4 (2GB) + Custom Carrier Board (2x CSI nativ) | -30 EUR |
| GenX320 OEM-Preis bei 10+ Stueck | -100 EUR (geschaetzt) |
| Kleinerer Akku (24V 50Ah, reicht bei Solar) | -200 EUR |
| 1x Solarpanel statt 2x | -50 EUR |
| Mengenrabatt | -50 EUR |
| EG25-G direkt auf Custom Board (kein Sixfab HAT) | -45 EUR |
| **Reduzierte Stueckkosten** | **~1.112 EUR** |

> Knapp ueber 1.000 EUR Ziel. Fuer Serie: GenX320-Chip (~$10) + EG25-G on-board + eigenes PCB
> → Ziel ~500 EUR/Stueck realistisch.

---

## 4. BLOCKSCHALTBILD

```
┌──────────────────────────────────────────────────────────────────┐
│                      ELEKTRONIK-BOX (IP65, pfostenmontiert)      │
│                                                                  │
│  ┌────────────┐    ┌───────────┐    ┌─────────────────────┐     │
│  │ 2x Solar   │───▶│ Victron   │───▶│  ← 24V von         │     │
│  │ 50W Serie  │    │ SmartSolar│    │    Akku-Box (Boden) │     │
│  │ (~44V Voc) │    │ 100/20    │    └──────────┬──────────┘     │
│  └────────────┘    └───────────┘               │ 24V            │
│                                     ┌──────────▼──────────┐     │
│                                     │  Witty Pi 4 Mini    │     │
│                                     │  (Power Mgmt + RTC) │     │
│                                     └──────────┬──────────┘     │
│                                                │                │
│                                     ┌──────────▼──────────┐     │
│                                     │  DC-DC 24V → 5V     │     │
│                                     │  (Step-Down, 5A)    │     │
│                                     └──────────┬──────────┘     │
│                                                │ USB-C          │
│  ┌────────────┐   CAM0 (CSI-2)     ┌──────────▼──────────┐     │
│  │  GenX320   │◀───────────────────▶│                     │     │
│  │  Event-Cam │                     │   Raspberry Pi 5    │     │
│  └────────────┘                     │     (4GB RAM)       │     │
│                                     │                     │     │
│  ┌────────────┐   CAM1 (CSI-2)     │   ┌─────┐ ┌─────┐  │     │
│  │  64MP      │◀───────────────────▶│   │SD   │ │USB  │  │     │
│  │  Arducam   │                     │   │Card │ │Stick│  │     │
│  └────────────┘                     │   └─────┘ └─────┘  │     │
│                                     │                     │     │
│                                     └──┬────┬────┬────┬──┘     │
│                                        │    │    │    │         │
│  ┌────────────┐   USB (via Ext.)      │    │    │    │         │
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
│  ┌──────────────────┐  VE.Direct-to-USB        │    │         │
│  │ Victron SmartShunt│◀────────────────────────┘    │         │
│  │ 500A/50mV        │  (/dev/ttyUSB0)              │         │
│  │ (im Akku-Minus)  │                              │         │
│  └──────────────────┘                              │         │
│                                         ┌──────▼────┐         │
│                                         │LTE Antenne│         │
│                                         └───────────┘         │
└──────────────────────────────────────────────────────┘         │
                                                                  │
  ┌──────────────────────┐                                       │
  │    AKKU-BOX          │  24V Kabel (wetterfeste Stecker)      │
  │    (IP65, am Boden)  │◀──────────────────────────────────────┘
  │                      │
  │  LiFePO4 24V 100Ah  │
  │  ~20 kg              │
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

**Stattdessen:** Ein monolithischer Python-Prozess (`bugsy-daemon`) als einziger systemd-Service.
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
│  │          bugsy-daemon (ein Python-Prozess)         │    │
│  │          systemd Service (Restart=always)          │    │
│  │                                                    │    │
│  │  ┌─────────────────────────────────────────────┐   │    │
│  │  │  Event-Erkennung (Thread)                   │   │    │
│  │  │  OpenEB + GenX320 Event-Stream (CAM0)       │   │    │
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
│  │  + Python 3 + OpenEB + libcamera/Picamera2         │    │
│  │  + zigpy + bellows (Zigbee direkt)                 │    │
│  │  + httpx + qmicli (LTE Upload)                     │    │
│  └────────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────────┘
```

### 5.1 Event-basierter Erkennungsalgorithmus

```
┌──────────────┐
│  GenX320     │    Asynchroner Event-Stream (CAM0)
│  Event-Cam   │    (nur bei Pixel-Aenderung)
│  320x320     │
│  <50 mW      │
└──────┬───────┘
       │ Events (x, y, timestamp, polarity)
       ▼
┌──────────────┐
│  OpenEB      │    Event-Clustering + Filterung
│  Pipeline    │    - Rausch-Events filtern (AFK)
│              │    - Raeumliche Cluster bilden
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
| Solarpanels 2x 50W | ~5.0 kg |
| Elektronikbox (Gehaeuse + Pi + Sixfab HAT + Kameras + MPPT) | ~2.0 kg |
| Kontrastschirm (PVC/HPL) | ~1.0 kg |
| Aluminium-Pfosten (2x) | ~2.0 kg |
| Querstrebe + Montage | ~1.0 kg |
| Kabel + Sonstiges | ~0.5 kg |
| **Pfosten-Gesamt** | **~11.5 kg** |

### Boden-Komponenten

| Komponente | Gewicht |
|-----------|---------|
| LiFePO4 Akku 24V 100Ah | ~21 kg |
| Akku-Box (Gehaeuse) | ~2 kg |
| **Boden-Gesamt** | **~23 kg** |

### Transport-Gesamt: ~34.5 kg (in 2 Teilen transportierbar)

---

## 7. ABMESSUNGEN

| Element | Abmessungen |
|---------|------------|
| Elektronikbox | 25 x 20 x 12 cm |
| Akku-Box | 60 x 25 x 25 cm |
| Kontrastschirm | 60 x 60 cm |
| Solarpanels (2x) | je 70 x 55 x 3 cm |
| Pfosten (ueber Boden) | 40 x 40 mm, ~120 cm |
| Pfostenabstand | ~70 cm |
| Gesamthoehe (ueber Boden) | ~150 cm |

---

## 8. BESCHAFFUNGSLISTE (EINKAUF)

| Quelle | Komponenten |
|--------|------------|
| **Sixfab** (sixfab.com) | 4G/LTE Modem Kit (Base HAT + EG25-G + Antennen) |
| **Prophesee** (prophesee.ai) | GenX320 Starter Kit fuer RPi 5 |
| **BerryBase.de** | Pi 5, Kabel |
| **Welectron.com / Amazon.de** | Arducam 64MP Hawkeye |
| **Amazon.de** | LiFePO4 24V 100Ah (LiTime/Redodo ~440 EUR), SONOFF ZBDongle-E, SONOFF SNZB-02WD, DC-DC Wandler, Gehaeuse |
| **Offgridtec.com / Amazon.de** | Victron SmartSolar 100/20, Solarpanels |
| **Offgridtec.com / SVB24.com** | Victron SmartShunt 500A/50mV, VE.Direct-to-USB Kabel |
| **Reichelt.de / Conrad.de** | Kabelverschraubungen, Klemmen, Kleinteile |
| **Baumarkt** | Alu-Pfosten, Bodenhuelsen, PVC-Platte, Montagematerial |

---

## 9. RISIKEN UND MASSNAHMEN

| Risiko | Wahrsch. | Auswirkung | Massnahme |
|--------|----------|------------|-----------|
| GenX320 nicht lieferbar / zu teuer | Mittel | Hoch | Fallback: iniVation DVXplorer Lite (1.900 EUR, USB) oder OpenCV Frame-Diff |
| Sixfab Modem-Boot zu langsam (>30 Sek) | Niedrig | Niedrig | Upload-Intervall vergroessern; Modem laenger eingeschaltet lassen |
| LTE-Empfang im Feld schlecht | Mittel | Mittel | Externe SMA-Antenne mit Verlaengerung; SIM-Karte eines anderen Anbieters testen |
| SIM-Datenvolumen aufgebraucht | Niedrig | Mittel | 1NCE 500MB reicht ~11 Monate; Monitoring via Telemetrie; Thumbnails nur bei Bedarf |
| Zigbee-Interferenz mit Pi 5 USB 3.0 | Mittel | Niedrig | USB-Verlaengerungskabel (15-20cm) als Abstandshalter |
| 24V Akku zu schwer fuer Transport | Niedrig | Niedrig | Zweiteiliger Aufbau (Pfosten + Bodenbox); Sackkarre fuer Transport |
| Kondenswasser in Kamerabox | Mittel | Hoch | Silica-Gel; Membranfilter-Belueftung |
| USB-Stick Korruption | Niedrig | Hoch | ext4 Journaling; Write-Ahead-Log; regelmaessige fsck |

---

## 10. EMPFOHLENE NAECHSTE SCHRITTE

1. **Sofort:** GenX320 Starter Kit bei Prophesee anfragen (Preis + Lieferzeit)
2. **Sofort:** Sixfab 4G/LTE Modem Kit bestellen (sixfab.com) + IoT SIM-Karte (z.B. 1NCE)
3. **Parallel:** Pi 5, Arducam 64MP, SONOFF Zigbee-Komponenten bestellen
4. **Woche 1-2:** Laborprototyp am Tisch:
   - Pi 5 + GenX320 (CAM0) + 64MP (CAM1) gleichzeitig testen
   - Sixfab HAT: GPIO16 Power Control, QMI-Anbindung, HTTPS Upload testen
   - Tailscale/SSH ueber Sixfab LTE testen
   - zigpy/bellows + SNZB-02WD: Sensor-Datenempfang testen (direkt, ohne Zigbee2MQTT)
5. **Woche 2-3:** Trigger-Logik: Event-Clustering → 64MP Aufnahme → Thumbnail → LTE Upload
6. **Woche 3-4:** Remote-Konfiguration via HTTPS Polling, OTA-Update-Mechanismus
7. **Woche 4-5:** Gehaeusebau, 24V Stromversorgung integrieren, Feldtest
8. **Woche 5-8:** Iteration, 2 weitere Prototypen

> **Kritischer Pfad:** GenX320 Starter Kit Verfuegbarkeit.
> Parallel-Strategie: Prototyp 1 kann mit OpenCV Frame-Diff starten (ohne GenX320),
> GenX320 als Upgrade in Prototyp 2/3.

---

## 11. EVOLUTIONSPFAD (PROTOTYP → PILOT → SERIE)

| Phase | Plattform | Trigger | Aufnahme | Akku | Konnektivitaet | Stueckkosten |
|-------|-----------|---------|----------|------|----------------|-------------|
| **Prototyp** | Pi 5 (Dual-CSI) | GenX320 | 64MP Arducam | 24V 100Ah | Sixfab EG25-G | ~1.732 EUR |
| **Pilot** | CM4 + Custom Board | GenX320 | 12MP Pi Cam 3 | 24V 50Ah | EG25-G direkt | ~1.100 EUR |
| **Serie** | Custom SoM | GenX320 on-board | OEM 12MP | 24V 30Ah | Quectel EG25-G OEM | ~500 EUR (Ziel) |

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
| **0.6.0** | **2026-03-05** | **Monolithische Architektur: MQTT/Mosquitto/Zigbee2MQTT/Node.js entfernt; ein Python-Prozess (bugsy-daemon); Zigbee direkt via zigpy/bellows; Cloud-Upload via HTTPS statt MQTT; ~150 MB RAM gespart; weniger Fehlermodi** |
