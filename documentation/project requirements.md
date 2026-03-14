ANFORDERUNGSKATALOG
Autarkes Gerät zur Erkennung und Zählung von Insekten im Feld
Dokumentstatus
•	Projektname: BUGSI
•	Version: 0.0.1
•	Datum: 2026-02-26
•	Erstellt von: Jan Nordhoff
•	Freigabe durch:

•	Einsatzregion / Feldtyp: Agrar, Deutschland
•	Stakeholder: Landwirt, Forschung, Behörde 
•	Zieltermin Prototyp / Pilot / Serie: 31.03.2026 / 30.06.2026 / …
1. PROJEKTZIEL
1.1 ZIELBESCHREIBUNG
 
2 Stangen im Boden, Schirm im Hintergrund, Kamerabox davor
Das System soll Insekten auf landwirtschaftlichen Flächen automatisch erfassen und zählen.
Es soll autark betrieben werden können und Messdaten lokal speichern sowie optional übertragen.
Auf das Gerät soll über remote zugegriffen werden.
Es soll eine Plattform für das Empfangen der Daten entwickelt werden. Diese muss günstig und herstellerunabhängig betrieben werden können.

1.2 NICHT-ZIELE (WICHTIG)
Was soll das Gerät nicht leisten? (verhindert Fehlannahmen)
•	Keine vollständige Artenbestimmung auf wissenschaftlichem Niveau
•	Keine Bekämpfung von Insekten
•	Kein Echtzeit-Tracking einzelner Tiere über größere Distanzen
•	Keine Insekten fangen
2. EINSATZSZENARIO UND ANWENDUNGSFALL
2.1 ANWENDUNGSZWECK
•	Forschung / Monitoring
•	Schädlingsfrüherkennung
•	Bestäuber-Monitoring
•	Landwirtschaftliche Praxis (Entscheidungsunterstützung)
2.2 EINSATZUMGEBUNG
•	Kulturart / Feldtyp: Agrar
•	Region / Klima: Deutschland
•	Saison / Einsatzzeitraum: Insektenaktivitätszeit (Mitte März – Mitte Oktober)
•	Typische Wetterbedingungen: 5-40 °C
•	Besondere Belastungen: Staub, Regen, Spritzmittel, Tiere
2.3 BETRIEBSMODUS
•	Nur tagsüber
•	Ereignisbasiert (Trigger): wenn Insekt festgestellt wird
3. FACHLICHE ANFORDERUNGEN (WAS SOLL ERKANNT/GEZÄHLT WERDEN?)
3.1 ZIELINSEKTEN
•	Zielgruppe: Bestäuber, Schadinsekten (Krabbeln), alle fliegenden Insekten.
•	Zielarten: Schmetterlinge, Wildbienen, Schlupfwespen, Laufkäfer
o	@Ami : Erstellt Liste mit Feldbewohnern
•	Körpergröße (ca.): von 5 mm bis 60 mm
•	Verhalten:
o	fliegend
o	krabbelnd
o	beides

3.2 ERKENNUNGSZIEL
Plattform (online):
•	Nur Zählung gesamt
•	Zählung nach Gruppen (z. B. Biene/Käfer/Motte)
•	Nachweis einzelner Zielschädlinge
3.3 QUALITÄTSANFORDERUNGEN AN DIE ERKENNUNG
•	Zielgenauigkeit Zählung: ___ %
•	Zielgenauigkeit Klassifikation (falls relevant): ___ %
•	Max. tolerierte Fehlzählung: ___ %
•	Wichtiger zu minimieren:
o	False Positives (zu viel gezählt)
o	beides gleich wichtig
3.4 DOPPELZÄHLUNGEN / WIEDERHOLUNGEN
Wie soll verhindert werden, dass ein Insekt mehrfach gezählt wird?
•	Eher kritisch
•	Ansatz (z. B. Zeitfenster, Geometrie, Tracking): Zeitfenster, nach N Sekunden neues Bild
4. MESSPRINZIP UND SYSTEMKONZEPT
4.1 ZULÄSSIGE MESSPRINZIPIEN
Bitte markieren:
•	Kamera / Bildverarbeitung
•	Akustik / Mikrofon (optional) -> AudioMoth ?
4.2 BIOLOGISCHE / ETHISCHE RANDBEDINGUNGEN
•	Nicht-invasive Erfassung (keine Falle)
4.3 ERFASSUNGSBEREICH
•	Freifeld-Erfassung (offene Umgebung)
•	Messbereich / Geometrie: Boden/Pflanze
5. BETRIEBSANFORDERUNGEN UND AUTARKIE
5.1 DEFINITION „AUTARK“
Was bedeutet autark im Projekt?
•	Kein Netzstrom
•	Kein Bedienpersonal vor Ort
•	Vollautomatischer Betrieb für min. 2 Wochen
5.2 LAUFZEIT OHNE WARTUNG
•	Mindestlaufzeit: 14Tage
•	Ziel-Laufzeit: 8 Monate
5.3 ENERGIEVERSORGUNG
•	Solar + Akku
o	Kleinere Panels 70x50cm, vll auch mehrere?
•	Wechselakku
•	Mindestlaufzeit ohne Sonne: 5 Tage
•	Power-Budget Ziel: ___ Wh/Tag - 
Anforderungen:
•	Erlaubte Baugröße für Energieversorgung:
•	Winterbetrieb nötig? nein
5.4 START-/RESTART-VERHALTEN
•	Muss das System nach Stromausfall automatisch starten?
o	ja
•	Datenverlust bei Neustart zulässig?
o	nein
6. UMGEBUNGS- UND ROBUSTHEITSANFORDERUNGEN
6.1 UMWELTBEDINGUNGEN
•	Betriebstemperatur: von 0 °C bis 40 °C
•	Lagertemperatur: dran schreiben
•	Luftfeuchtigkeit: 100 % (Regen)
•	Regen/Spritzwasser: ja
•	Staubbelastung: ja
•	Wind/Vibration: ja
6.2 SCHUTZANFORDERUNGEN
•	Gewünschte Schutzklasse (IP): 65 – Staubdicht und Geschützt vor Strahlwasser (Düse) aus beliebigem Winkel)
•	UV-Beständigkeit Gehäuse: ja
6.3 MECHANISCHE ANFORDERUNGEN
•	Montageart: Pfosten, (zur Not zusätzlich Box auf Boden)
•	Montagehöhe: 0-1,5 m
•	Max. Gewicht: 15 kg
•	Max. Abmessungen: 50 x 50 x 50 cm
•	Aufbauzeit vor Ort max.: 30 Minuten
7. DATENANFORDERUNGEN
7.1 ZU SPEICHERNDE DATEN
Bitte auswählen:
•	Zeitstempel
•	Rohbilder
•	Umweltwerte (Temp./Feuchte) 
•	Geräte-Statusdaten (Akku, Fehler)
7.2 DATENAUFLÖSUNG / MESSINTERVALL
•	Messmodus: 
o	Ereignisbasiert, dann N sec Pause
•	Ausgabeintervall: alle 1 Stunden
o	„Proben“ + Zustand -> an Service
7.3 SPEICHERUNG
•	Lokaler Speicher nötig: ja
o	Speichergroße __ GB – Ausrechnen
	USB Stick? Einfacher Tausch
7.4 DATENFORMAT / EXPORT
•	USB-Stick
•	(Online)
8. KOMMUNIKATION UND VERNETZUNG
8.1 VERFÜGBARE INFRASTRUKTUR AM FELD
•	Mobilfunk (LTE/5G)
8.2 KOMMUNIKATIONSANFORDERUNGEN
•	Datenübertragung:
o	periodisch
•	Max. Datenvolumen pro Tag: ___ MB - ausrechnen
•	Verbindungsabbrüche tolerierbar: ja
8.3 FERNWARTUNG
•	Statusabfrage remote
•	Konfiguration remote
•	Software-Updates remote (OTA)
•	Neustart remote
8.4 SCHNITTSTELLE FÜR SERVICE
Folgende Schnittstellen werden benötigt:
•	USB-Stick
•	SD-Karte
9. ELEKTRONIK UND RECHENPLATTFORM & SOFTWARE- UND ERKENNUNGSLOGIK
9.1 PLATTFORM
•	SBC (z. B. Raspberry Pi)
9.2 SENSORIK
•	Kamera: 
o	Auflösung 64MP/32MP 
•	Weitere Sensoren: Feuchte/Temperatur
9.3 UPDATEFÄHIGKEIT
•	Firmware-Updates: 
o	OTA
•	Konfigurationsänderungen im Feld: 
o	Ja
9.4 VERARBEITUNGSORT
•	Zentral / Server / Cloud
9.5 ERKENNUNGSVERFAHREN
Zentral:
•	KI/ML-Modell
9.6 MODELLE / TRAININGSDATEN (OPTIONAL)
•	Trainingsdaten vorhanden? jaein
•	Anzahl Beispiele (ca.):
•	Labelqualität:
9.8 KONFIGURIERBARKEIT
Welche Parameter sollen einstellbar sein?
•	Erkennungsschwellen
•	Messzeiten
•	Übertragungsintervall
•	Trigger-Logik
9.10 NACHVOLLZIEHBARKEIT
•	Nachweisdaten: 
o	Snapshot bei Ereignis
o	tägliche Stichprobe
o	keine
•	Logging-Level:  Einstellbar
o	minimal 
o	standard
o	debug

10. VALIDIERUNG UND QUALITÄTSSICHERUNG
10.1 REFERENZMESSUNG
Wie wird die Funktion überprüft?
•	Manuelle Zählung
10.2 TESTKRITERIEN
Abnahmekriterien definieren (messbar):
•	Zählgenauigkeit mindestens 90 %
•	Laufzeit ohne Wartung mindestens 5 Tage
10.3 KALIBRIERUNG
•	Kalibrierung erforderlich? ja
•	Wenn ja:
o	bei Inbetriebnahme
	Bei Power-On -> Bild in die Cloud
10.4 SELBSTDIAGNOSE
Soll das Gerät Fehler selbst erkennen?
•	Akkustand niedrig
•	Sensor/Kamera blockiert
•	Speicher voll
11. WARTUNG UND BETRIEB
11.1 WARTUNGSINTERVALLE
•	Regelmäßige Wartung alle: 14 Tage
•	Typische Wartungsarbeiten:
o	Reinigung
o	USB-Stick tauschen
o	Akkuwechsel (wenn unbedingt nötig)
o	Sichtprüfung
o	Firmware-Update (Tausch SD-Karte) (wenn nötig)
11.2 AUSTAUSCHBARKEIT
•	Müssen Komponenten modular tauschbar sein?
o	ja
•	Welche Module?
o	Akku
o	USB Stick (Speicher)
11.3 BEDIENBARKEIT
•	Wer betreibt das System?
o	Forschungsteam
•	Lokale Anzeige:
o	keine
12. RECHTLICHE UND NORMATIVE ANFORDERUNGEN
12.1 DATENSCHUTZ
•	nicht relevant
12.2 ZULASSUNGEN / NORMEN
•	nein
12.3 NATURSCHUTZ / ETHIK
•	Nicht-tödliches Monitoring erforderlich
13. KOSTEN UND WIRTSCHAFTLICHKEIT
13.1 BUDGET
•	Zielkosten Prototyp: 5000 € - ausrechnen
•	Zielkosten Pilotgerät: 1000 € - ausrechnen
•	Zielkosten Serie (pro Stück): ___ €
13.2 STÜCKZAHLEN
•	Phase 1 (Prototyp): 3 Stück
•	Phase 2 (Pilot): 3 Stück
•	Phase 3 (Skalierung): ___ Stück
13.3 BETRIEBSKOSTEN
•	Datenkosten / Connectivity: 8 €/Gerät
•	Cloud Kosten
14. PROJEKTPHASEN UND MEILENSTEINE
14.2 PRIORISIERUNG (MUSS / SOLL / KANN)
Für jede Anforderung markieren:
•	MUSS (zwingend)
o	Gerät mit Akku + Solar
o	Gerät mit Events + Kamera
o	Cloud Service
o	OTA Update + Status
•	SOLL (wichtig)
o	Externe Sensoren (Temperatur/Feuchte)
•	KANN (optional)
o	Audio
14.3 LIEFERGEGENSTÄNDE
•	Hardware: Gerät(e), Zubehör, Montagekit
•	Software: Firmware, Auswerte-Tool, Konfig-Tool
•	Dokumentation: Schaltplan, Stückliste, Bedienung, Wartung, Datenschema
•	Testprotokolle: Validierung
