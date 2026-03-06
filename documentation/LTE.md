# LTE-Module: Alternativen zur Blues Notecard

**Anforderungen:** Eigene SIM-Karte, USB-Anschluss, niedriger Stromverbrauch, abschaltbar wenn nicht in Verwendung.

---

## Vergleichstabelle

| Feature | Waveshare SIM7600G-H HAT | EXVIST EC25-EU Dongle | Huawei E3372h-320 | Waveshare SIM7080G HAT | Sixfab EG25-G Kit |
|---|---|---|---|---|---|
| **LTE Cat** | Cat-4 | Cat-4 | Cat-4 | Cat-M1 / NB-IoT | Cat-4 |
| **Max Download** | 150 Mbps | 150 Mbps | 150 Mbps | 1.1 Mbps | 150 Mbps |
| **Form Factor** | HAT | USB Stick | USB Stick | HAT | HAT + mPCIe |
| **SIM Typ** | Standard (2FF) | Micro (3FF) | Standard (2FF) | Nano (4FF), nur 1.8V | Micro (3FF) |
| **DE Baender** | B1/3/7/8/20/28 | B1/3/7/8/20/28A | B1/3/7/8/20/28 | B1/3/8/20/28 (kein B7) | B1/3/7/8/20/28 |
| **Idle Verbrauch** | ~150 mA (System) | ~100-200 mA (USB) | ~150-250 mA (USB) | ~39 mA (System) | ~30-50 mA (HAT) |
| **Sleep/PSM** | ~2-20 mA | ~1.1 mA (Modul) | Keiner (HiLink) | **3.2 uA (PSM)** | ~1.8 mA (Modul) |
| **Abschaltung** | GPIO6 + AT Cmd | USB Power Cut | USB Power Cut | GPIO + AT Cmd | **GPIO16 HW Cutoff** |
| **Preis (EUR)** | ~77-90 | ~60-70 | ~35-60 | **~35** | ~125 (Kit) |
| **GPS/GNSS** | Ja | Ja (optional) | Nein | Ja | Ja |
| **Linux Support** | QMI/PPP/AT | QMI/PPP/AT/MBIM | Ethernet (HiLink) | PPP/AT | QMI/PPP/AT/MBIM |
| **SSH/Tailscale** | Ja (volle IP) | Ja (volle IP) | Ja (doppel-NAT) | Nein (zu langsam) | Ja (volle IP) |

---

## 1. Waveshare SIM7600G-H 4G HAT (B)

**Hersteller:** Waveshare (Modul: SIMCom SIM7600G-H)
**Preis:** ~77-90 EUR
**Typ:** Raspberry Pi HAT (40-pin GPIO Header), zusaetzlich USB und UART

### Spezifikationen

| Parameter | Wert |
|---|---|
| LTE Kategorie | Cat-4 (150 Mbps DL / 50 Mbps UL) |
| LTE Baender (FDD) | B1/B2/B3/B4/B5/B7/B8/B12/B13/B18/B19/B20/B25/B26/B28/B66 |
| LTE Baender (TDD) | B34/B38/B39/B40/B41 |
| SIM Karte | Standard SIM (2FF), 1.8V/3V |
| GNSS | GPS, GLONASS, BeiDou, Galileo |
| Fallback | 3G / 2G |

### Stromverbrauch

| Modus | Verbrauch |
|---|---|
| Idle (Netz verbunden) | ~150 mA (System, 5V USB) |
| Sleep (AT+CSCLK=1, DTR high) | ~2-3 mA (Modul), ~20 mA (Board mit USB) |
| Power Down | ~10 uA (Modul), 2-3 mA (Board quiescent) |
| Senden (Burst) | bis 2A Peak |

### Abschaltung

- **GPIO:** Jumper PWR→D6, dann RPi GPIO6 steuert PWRKEY (3-5 Sek. low → Modul aus)
- **AT Befehle:** `AT+CPOF` (Power Down), `AT+CFUN=0` (RF aus), `AT+CSCLK=1` (Sleep)
- **Manuell:** PWRKEY Taster auf dem HAT

### Linux-Kompatibilitaet

- QMI, PPP, AT Command Interface
- Standard CDC-ACM/option Treiber
- NetworkManager / ModemManager kompatibel
- Waveshare stellt Python/C Beispielcode bereit

### Bewertung

| Pro | Contra |
|---|---|
| Alle DE-Baender abgedeckt | Relativ hoher Idle-Verbrauch (~150 mA) |
| GPIO-Power-Control vorhanden | HAT belegt GPIO Header (Stacking noetig) |
| GNSS integriert | Standard-SIM Slot (Adapter fuer Nano) |
| Gute Linux-Unterstuetzung | Board-Quiescent ~2-3 mA auch bei Modul-Off |
| Volle IP-Konnektivitaet (SSH/Tailscale) | |

**Bezug:** welectron.com, eckstein-shop.de, Amazon.de

---

## 2. EXVIST 4G LTE USB Dongle (Quectel EC25-EU)

**Hersteller:** EXVIST (Modul: Quectel EC25-EU)
**Preis:** ~60-70 EUR
**Typ:** USB Stick (USB-A)

### Spezifikationen

| Parameter | Wert |
|---|---|
| LTE Kategorie | Cat-4 (150 Mbps DL / 50 Mbps UL) |
| LTE Baender (FDD) | B1/B3/B7/B8/B20/B28A |
| LTE Baender (TDD) | B38/B40/B41 |
| SIM Karte | Micro SIM (3FF), Push-Push Slot |
| GNSS | GPS (optionaler IPEX Antennenanschluss) |
| Fallback | 3G / 2G |

### Stromverbrauch

| Modus | Verbrauch |
|---|---|
| Idle | ~21 mA (Modul), ~100-200 mA (USB gesamt) |
| Sleep (AT+QSCLK=1) | ~1.1 mA (Modul) |
| Power Off | ~10 uA (Modul) |
| Senden | bis ~1A Peak |

### Abschaltung

- **USB Power Cut:** `uhubctl` (Pi 5 USB Ports ganged → alle Ports gleichzeitig), oder externer USB-Hub mit Per-Port-Power
- **AT Befehle:** `AT+QPOWD` (Power Down), `AT+CFUN=0` (Airplane), `AT+QSCLK=1` (Sleep)
- **Praxisloesung:** GPIO-gesteuerter MOSFET/Relay am 5V USB, oder USB-Hub mit Per-Port-Steuerung

### Linux-Kompatibilitaet

- QMI (`qmi_wwan`), MBIM, PPP, AT Command
- Standard `option` USB Serial Treiber (Kernel 4.x+)
- NetworkManager / ModemManager kompatibel
- Keine Spezial-Treiber noetig

### Bewertung

| Pro | Contra |
|---|---|
| Kompakter USB-Stick | Kein Hardware-Power-Control (nur USB Power Cut) |
| Alle DE-Baender | USB-Port-Power auf Pi 5 nicht individuell steuerbar |
| Hervorragender Linux-Support (QMI/MBIM) | Braucht externen USB-Hub oder MOSFET fuer Power Control |
| TTL Serial Breakout Pins vorhanden | Keine offizielle DE-Bezugsquelle |
| Guenstiger als HAT-Loesungen | |

**Bezug:** Amazon.com (internationaler Versand), AliExpress

---

## 3. Huawei E3372h-320 (Brovi E3372-325)

**Hersteller:** Huawei
**Preis:** ~35-60 EUR
**Typ:** USB Stick (USB-A)

### Spezifikationen

| Parameter | Wert |
|---|---|
| LTE Kategorie | Cat-4 (150 Mbps DL / 50 Mbps UL) |
| LTE Baender (FDD) | B1/B3/B7/B8/B20/B28 |
| SIM Karte | Standard SIM (2FF) |
| GNSS | Nein |
| Fallback | 3G / 2G |

### Stromverbrauch

| Modus | Verbrauch |
|---|---|
| Idle (HiLink Modus) | ~150-250 mA (USB, interner Router laeuft) |
| Sleep | **Keiner verfuegbar** (HiLink-Firmware hat keinen Sleep) |
| Power Off | Nur durch USB Power Cut (0 mA) |
| Senden | ~400-600 mA Peak |

### Abschaltung

- **Nur USB Power Cut:** `uhubctl`, GPIO-MOSFET, oder externer USB-Hub
- **Kein AT-Zugriff:** HiLink-Firmware blockiert AT Commands
- **Kein Sleep-Modus:** Interner Linux-Router laeuft immer

### Linux-Kompatibilitaet

- Erscheint als USB-Ethernet-Adapter (RNDIS / CDC-Ethernet) → Plug-and-Play
- **Kein Modem-Modus** in Standard-HiLink-Firmware
- Doppel-NAT (interner Router auf 192.168.8.1)
- Web-Interface fuer Konfiguration

### Bewertung

| Pro | Contra |
|---|---|
| Guenstigster Preis (~35 EUR) | **Kein Sleep-Modus** (hoher Dauerverbrauch) |
| Plug-and-Play (USB Ethernet) | Kein AT Command Zugriff (HiLink) |
| Ueberall erhaeltlich (Amazon.de) | **Doppel-NAT** (problematisch fuer Tailscale) |
| Alle DE-Baender | Kein GPS |
| Einfachste Einrichtung | Kein feingranulares Power Management |
| | **Nicht empfohlen fuer IoT/Feldeinsatz** |

**Bezug:** Amazon.de, Saturn, MediaMarkt

---

## 4. Waveshare SIM7080G Cat-M/NB-IoT HAT

**Hersteller:** Waveshare (Modul: SIMCom SIM7080G)
**Preis:** ~35 EUR
**Typ:** Raspberry Pi HAT (40-pin GPIO Header), USB und UART

### Spezifikationen

| Parameter | Wert |
|---|---|
| LTE Kategorie | Cat-M1 (eMTC) + NB-IoT |
| Max. Download | Cat-M: 1.1 Mbps / NB-IoT: 136 kbps |
| Cat-M Baender | B1/B2/B3/B4/B5/B8/B12/B13/B14/B18/B19/B20/B25/B26/B27/B28/B66/B85 |
| NB-IoT Baender | B1/B2/B3/B4/B5/B8/B12/B13/B18/B19/B20/B25/B26/B28/B66/B71/B85 |
| SIM Karte | Nano SIM (4FF), **nur 1.8V** |
| GNSS | GPS, GLONASS, BeiDou, Galileo |

### Stromverbrauch

| Modus | Verbrauch |
|---|---|
| Idle | 10 mA (Modul), ~39 mA (System) |
| Sleep | 1.2 mA |
| **PSM (Power Saving Mode)** | **3.2 uA** |
| eDRX (81.92s) | 0.59 mA |
| Senden (Class 5) | ~33 mA bei 3.8V |

### Abschaltung

- **GPIO:** P7 Pin steuert PWRKEY (~1 Sek. halten fuer Power Toggle)
- **AT Befehle:** `AT+CPOWD=1` (Power Down), `AT+CFUN=0` (Minimum), `AT+CPSMS=1,...` (PSM → 3.2 uA)
- **PSM/eDRX:** Modul bleibt im Netz registriert bei Mikro-Ampere Verbrauch
- **Manuell:** PWRKEY Taster auf dem HAT

### Linux-Kompatibilitaet

- AT Command Interface via USB oder UART (`/dev/ttyUSB0` oder `/dev/ttyS0`)
- PPP fuer Datenverbindung
- TCP/UDP/HTTP/HTTPS/MQTT/CoAP/LWM2M direkt im Modem-Firmware
- Python und C Beispielcode von Waveshare

### Bewertung

| Pro | Contra |
|---|---|
| **Niedrigster Stromverbrauch aller Optionen** | **Sehr niedrige Datenrate** (max. 1.1 Mbps) |
| PSM: 3.2 uA (quasi aus, aber netzregistriert) | **Kein SSH/Tailscale moeglich** (zu langsam) |
| Guenstigster Preis (~35 EUR) | Cat-M/NB-IoT SIM-Plan erforderlich |
| GNSS integriert | Nur 1.8V SIM-Karten unterstuetzt |
| MQTT/CoAP direkt im Modem | Kein B7 (fuer DE aber nicht kritisch) |
| GPIO Power Control | Fuer Thumbnail-Upload zu langsam |

> **Hinweis:** Cat-M1/NB-IoT erfordert spezielle SIM-Tarife. In DE: Telekom IoT, Vodafone IoT, 1NCE (~10 EUR/500MB fuer 10 Jahre).

**Bezug:** welectron.com, Botland, Amazon.de

---

## 5. Sixfab 4G/LTE Cellular Modem Kit (Quectel EG25-G)

**Hersteller:** Sixfab (Modul: Quectel EG25-G)
**Preis:** ~125 EUR (Kit: Base HAT + EG25-G + Antennen + Kabel)
**Typ:** Raspberry Pi HAT (Base HAT) + Mini PCIe Modul

### Spezifikationen

| Parameter | Wert |
|---|---|
| LTE Kategorie | Cat-4 (150 Mbps DL / 50 Mbps UL) |
| LTE Baender (FDD) | B1/B2/B3/B4/B5/B7/B8/B12/B13/B18/B19/B20/B25/B26/B28 |
| LTE Baender (TDD) | B38/B39/B40/B41 |
| SIM Karte | Micro SIM (3FF) |
| GNSS | GPS, GLONASS, BeiDou, Galileo, QZSS |
| Fallback | 3G / 2G |

### Stromverbrauch

| Modus | Verbrauch |
|---|---|
| Idle | ~21 mA (Modul), ~30-50 mA (HAT + Modul) |
| Sleep (AT+QSCLK=1) | ~1.8 mA (Modul) |
| Power Off (Modul) | ~15 uA |
| **GPIO HW Cutoff** | **0 mA (HAT komplett stromlos)** |
| Senden | bis ~1A Peak |

### Abschaltung

- **GPIO16 Hardware Power Cut:** `PWR_DSBLE_P` Pin → HIGH trennt die gesamte HAT-Stromversorgung (0 mA)
- **AT Befehle:** `AT+QPOWD` (Power Down), `AT+CFUN=0` (Airplane), `AT+QSCLK=1` (Sleep)
- **Empfohlene Sequenz:** `AT+QPOWD` → warten → GPIO16 HIGH → HAT komplett aus

### Linux-Kompatibilitaet

- QMI (empfohlen): `qmi_wwan` Treiber, `libqmi`, `udhcpc`
- Alternativ: PPP, MBIM, AT Commands
- NetworkManager / ModemManager kompatibel
- Sixfab bietet ausfuehrliche Dokumentation und Setup-Guides
- CE-zertifiziert

### Bewertung

| Pro | Contra |
|---|---|
| **Echte GPIO-Hardware-Abschaltung (0 mA)** | Hoechster Preis (~125 EUR) |
| Alle DE-Baender abgedeckt | HAT belegt GPIO Header |
| Bester Linux-Support (QMI/MBIM) | Sixfab CORE Cloud eingestellt (Dez 2025) |
| Modulares Design (mPCIe tauschbar) | Etwas groesserer Formfaktor |
| GNSS + MIMO integriert | |
| Niedrigster Idle-Verbrauch unter Cat-4 HATs | |
| Volle IP-Konnektivitaet (SSH/Tailscale) | |

**Bezug:** sixfab.com (Direktversand), Amazon
**Link:** https://www.amazon.de/Raspberry-Modem-Kit-Cloud-Software-Fernbedienung-Netzwerk%C3%BCberwachung/dp/B089X8N2TY/ref=sr_1_1?__mk_de_DE=%C3%85M%C3%85%C5%BD%C3%95%C3%91&crid=1P5531WAY6E50&dib=eyJ2IjoiMSJ9._yGmVv59TbeSn4IEGjq0oyyu2Fxd-yVebB6TgeDC-RjGjHj071QN20LucGBJIEps.OkDIVanGHfM8By4zWEUutfzuAEoeVLkPYLOEsxt72eU&dib_tag=se&keywords=sixfab+4g&qid=1772717255&sprefix=sixfab+4g%2Caps%2C197&sr=8-1 

---

## Empfehlung fuer BUGSY

### Primaerer LTE-Kanal (Telemetrie + Thumbnails)

**Waveshare SIM7600G-H HAT (~80 EUR)** oder **Sixfab EG25-G Kit (~125 EUR)**

| Kriterium | SIM7600G-H | Sixfab EG25-G |
|---|---|---|
| Abschaltbarkeit | GPIO + AT Cmd (gut) | **GPIO HW Cutoff (0 mA, best)** |
| Preis | ~80 EUR | ~125 EUR |
| Volle IP (SSH/Tailscale) | Ja | Ja |
| Thumbnail Upload | Ja (Cat-4) | Ja (Cat-4) |
| GNSS | Ja | Ja |

> Fuer BUGSY ist die **Sixfab-Loesung** optimal: GPIO16 schaltet das Modul
> **hardwareseitig komplett ab** (0 mA). Kein Quiescent-Strom, kein Sleep-Mode-Risiko.
> Bei stuendlichem Upload: Modul einschalten → Daten senden → Modul ausschalten.
> Verbrauch nur waehrend der ~2-5 Min Upload-Phase.

### Optionaler Zweitkanal (Remote-Zugang)

Falls SSH/Tailscale parallel zum Datenkanal benoetigt wird:
**Huawei E3372h-320 (~40 EUR)** als guenstiger Always-On USB-Stick (nur bei Bedarf anstecken).

### Nicht empfohlen fuer BUGSY

- **Waveshare SIM7080G:** Zu langsam fuer Thumbnail-Upload (~30 KB * 50 Events = 1.5 MB/Tag bei 136 kbps = ~90 Sek, akzeptabel, aber kein SSH moeglich)
- **Huawei E3372h-320 als Primaerkanal:** Kein Sleep, kein AT-Zugriff, Doppel-NAT, hoher Dauerverbrauch
