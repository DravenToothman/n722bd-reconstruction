"""Writes site/data/comms.json: timed radio captions and weather notes for the viewer.

Radio: machine transcription (faster-whisper medium.en) of the 116 s air-traffic-control clip, then checked and tidied by hand against
the NTSB's public account. Wording is uncertain where marked (unc=True). The audio file itself is NOT part of this repository.

Audio-to-UTC alignment: the clip has no clock. The pilot's own callouts ("descending ten thousand feet per minute", "overspeed
condition ... twenty thousand feet per minute") match the ADS-B descent at 17:48:28-17:48:37, which puts audio second 0 at about
17:47:29 UTC. The three callouts agree to about +/-4 s. The viewer has a +/-1 s nudge for the listener.

Weather notes come from public archives (see data/weather/): NWS Aviation Weather Center Convective SIGMET bulletins, METARs and
pilot reports, all via the Iowa Environmental Mesonet. SIGMET-polygon membership was checked by plotting the bulletin's reference
points (navaid positions from OurAirports; the Miami point uses the airport position, so it is approximate).
"""
import json
AUDIO_T0 = '17:47:29'
RADIO = [
 (0.56,  9.7, 'crew', "722BD, three five zero, moderate turbulence, plus or minus … seven hundred feet, six hundred feet.", True, None),
 (11.5, 14.0, 'atc',  "Roger, say outside air temperature?", False, None),
 (14.36,19.9, 'crew', "Negative forty-seven degrees Celsius. We're managing the ice, but it is moderate turbulence [for direct report?].", False, None),
 (20.44,25.6, 'atc',  "November 722BD, roger. Let me know if you need anything else. I'm just working [unclear] my airspace right now.", False, None),
 (26.1, 29.0, 'crew', "Thank you. If you have any better rides, let us know.", False, None),
 (29.72,37.6, 'atc',  "November 722BD, the rides do improve in my airspace. You're kind of far outside of it right now. You can expect better rides ahead.", False, None),
 (38.6, 45.2, 'crew', "Roger, 722BD. And now we're picking up precipitation. We need to climb to three seven zero, 722BD.", False, None),
 (45.72,51.7, 'atc',  "November 722BD, roger. Climb and maintain flight level three seven zero. [No further right than?] your present heading, for traffic.", True, None),
 (51.72,54.4, 'crew', "Climb three seven zero, 722BD.", False, None),
 (54.86,59.5, 'crew', "722BD, we're descending [eight?] thousand … mayday, mayday … we're descending ten thousand feet per minute.", True, None),
 (60.62,64.4, 'atc',  "November 722BD, roger. [unclear]", True, None),
 (64.64,69.9, 'crew', "722BD, we are in an overspeed condition, descending twenty thousand feet per minute.", False, "The machine transcript read 'overfeed'; the NTSB's account quotes 'overspeed condition'."),
 (70.46,74.9, 'atc',  "November 722BD, roger. [Altitude at your discretion?] Let me know what you need.", True, None),
 (77.38,79.8, 'crew', "We're going to crash into the ground, 722BD.", True, "Wording of this transmission is uncertain. Two machine passes agree, but press reports have quoted different words. Check the audio."),
 (81.84,84.5, 'atc',  "November 722BD, I'm here with you. Talk to me.", False, None),
 (85.02,91.1, 'crew', "We are descending [through?] twenty-two thousand feet, and we are banking sixty degrees.", True, "The numbers are uncertain. The track shows 25,000 ft and about 77° of bank at this moment."),
 (95.8, 97.4, 'atc',  "November 722BD, roger.", False, None),
 (100.52,102.8,'crew', "Look outside … [unclear] … look outside!", True, None),
 (106.24,111.0,'atc', "November 722BD. November 722BD. How do you hear?", False, None),
 (113.1,115.0,'atc',  "November 722BD, Miami.", False, None),
]
SRC_SIG = 'NWS Aviation Weather Center Convective SIGMET bulletins, via the Iowa Environmental Mesonet archive'
WEATHER = [
 ('15:37:12','sigmet','Thunderstorm SIGMETs already in effect',
  "Convective SIGMETs had been issued for Florida and its coastal waters every hour since at least 12:55 UTC (31E at 12:55, 35E at 13:55, 39E at 14:55, 42E at 15:55). Each described an area of thunderstorms moving little, with tops above 45,000 ft, covering south Florida.", SRC_SIG),
 ('16:55:00','sigmet','Convective SIGMET 45E issued',
  "Valid until 18:55 UTC. Florida and coastal waters: area of thunderstorms, moving little, tops above FL450. Its corners are about 70 nm southeast of Ormond Beach, 70 nm east of Miami, 50 nm east of Key West and 20 nm west-northwest of St. Petersburg. By my plotting of those points (the Miami corner is approximate) the jet was inside this area from 17:40 UTC, the earliest point I checked, until impact.", SRC_SIG),
 ('17:33:00','pirep','Other crews nearby (pilot reports)',
  "17:27 Gulfstream IV at FL260 near Miami: in cloud, light chop. 17:33 Boeing 737-800 at FL350 about 55 miles southeast of Palm Beach: light chop. Both were roughly 150 nm from N722BD at the time.", 'Pilot reports, via the Iowa Environmental Mesonet archive'),
 ('17:35:00','metar','Lantana (KLNA), about 3 miles from the impact site',
  "17:35 UTC: wind from 120° at 7 kt gusting 19, visibility 3 miles, thunderstorms in the vicinity, broken clouds at 2,900 ft, overcast at 3,700 ft, 26 °C.", 'KLNA METAR 011735Z'),
 ('17:41:00','sounding','Air at the jet\'s level',
  "From the Miami weather balloons (12:00 and 00:00 UTC, blended): about −48 °C at FL350, wind from 218° at 8 kt, winds under 14 kt at every level, freezing level near 15,000 ft. The crew reported −47 °C.", 'KMFL radiosondes, via the Iowa Environmental Mesonet archive'),
 ('17:42:00','metar','Fort Lauderdale (KFLL)',
  "17:42 UTC: wind from 110° at 17 kt gusting 26, light rain, visibility 6 miles, broken clouds at 1,500 ft, cumulonimbus to the northwest and northeast moving west.", 'KFLL METAR 011742Z'),
 ('17:45:00','pirep','Pilot report from a Learjet 60 (almost certainly N722BD)',
  "Filed with a 17:45 UTC time stamp: flight level 350, −46 °C, light clear ice, 25 nm west of Palm Beach. The radio call that matches it is heard in the clip at about 17:47:40.", 'Pilot report, via the Iowa Environmental Mesonet archive'),
 ('17:47:44','radar','Radar: into the top of a growing cell',
  "The path enters the upper part of a storm cell. Radar shows about 30 dBZ at the jet's altitude above a heavy core, with the cell top near 45,000 ft. Five minutes earlier the same spot showed only weak echo at that height.", 'Miami NEXRAD (KAMX) Level II, NOAA'),
 ('17:49:00','pirep','Urgent pilot report, 81 nm to the north',
  "17:49 UTC: a Citation near Melbourne reported moderate to severe turbulence at 18,000 ft.", 'Pilot report, via the Iowa Environmental Mesonet archive'),
 ('17:49:33','after','Afterwards',
  "17:53 UTC, Fort Lauderdale: heavy rain, cumulonimbus, broken clouds at 1,500 ft. 17:55 UTC: Convective SIGMET 48E issued for the same area, valid to 19:55 UTC. Lantana still reported thunderstorms in the vicinity at 17:55.", SRC_SIG + '; METARs'),
]
out = {'audioT0': AUDIO_T0, 'audioDur': 116.33,
  'radio': [dict(s=a, e=b, who=w, text=t, unc=u, note=n) for a, b, w, t, u, n in RADIO],
  'weather': [dict(t=t, kind=k, title=ti, body=b, src=s) for t, k, ti, b, s in WEATHER]}
json.dump(out, open('site/data/comms.json', 'w'), ensure_ascii=False, indent=1)
print('ok', len(RADIO), len(WEATHER))
