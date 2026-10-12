"""Approximate city-centre coordinates for major US cities (lat, lng).

Used so the most common start/finish choices resolve instantly, without a network call, even
when the city has no fuel station in the imported data. Accuracy of a few miles is plenty:
the routing service snaps these points to the nearest road.
"""

_RAW = """
Albany|NY|42.6526|-73.7562
Albuquerque|NM|35.0844|-106.6504
Atlanta|GA|33.7490|-84.3880
Austin|TX|30.2672|-97.7431
Baltimore|MD|39.2904|-76.6122
Billings|MT|45.7833|-108.5007
Birmingham|AL|33.5186|-86.8104
Boise|ID|43.6150|-116.2023
Boston|MA|42.3601|-71.0589
Buffalo|NY|42.8864|-78.8784
Charlotte|NC|35.2271|-80.8431
Cheyenne|WY|41.1400|-104.8202
Chicago|IL|41.8781|-87.6298
Cincinnati|OH|39.1031|-84.5120
Cleveland|OH|41.4993|-81.6944
Columbus|OH|39.9612|-82.9988
Dallas|TX|32.7767|-96.7970
Denver|CO|39.7392|-104.9903
Des Moines|IA|41.5868|-93.6250
Detroit|MI|42.3314|-83.0458
El Paso|TX|31.7619|-106.4850
Fort Worth|TX|32.7555|-97.3308
Fresno|CA|36.7378|-119.7871
Houston|TX|29.7604|-95.3698
Indianapolis|IN|39.7684|-86.1581
Jackson|MS|32.2988|-90.1848
Jacksonville|FL|30.3322|-81.6557
Kansas City|MO|39.0997|-94.5786
Las Vegas|NV|36.1699|-115.1398
Little Rock|AR|34.7465|-92.2896
Los Angeles|CA|34.0522|-118.2437
Louisville|KY|38.2527|-85.7585
Memphis|TN|35.1495|-90.0490
Miami|FL|25.7617|-80.1918
Milwaukee|WI|43.0389|-87.9065
Minneapolis|MN|44.9778|-93.2650
Nashville|TN|36.1627|-86.7816
New Orleans|LA|29.9511|-90.0715
New York|NY|40.7128|-74.0060
Oklahoma City|OK|35.4676|-97.5164
Omaha|NE|41.2565|-95.9345
Orlando|FL|28.5383|-81.3792
Philadelphia|PA|39.9526|-75.1652
Phoenix|AZ|33.4484|-112.0740
Pittsburgh|PA|40.4406|-79.9959
Portland|OR|45.5152|-122.6784
Raleigh|NC|35.7796|-78.6382
Richmond|VA|37.5407|-77.4360
Sacramento|CA|38.5816|-121.4944
Saint Louis|MO|38.6270|-90.1994
Salt Lake City|UT|40.7608|-111.8910
San Antonio|TX|29.4241|-98.4936
San Diego|CA|32.7157|-117.1611
San Francisco|CA|37.7749|-122.4194
San Jose|CA|37.3382|-121.8863
Seattle|WA|47.6062|-122.3321
Spokane|WA|47.6588|-117.4260
St. Louis|MO|38.6270|-90.1994
Tampa|FL|27.9506|-82.4572
Tucson|AZ|32.2226|-110.9747
Tulsa|OK|36.1540|-95.9928
Washington|DC|38.9072|-77.0369
"""

CITIES = {}
for _line in _RAW.strip().splitlines():
    _city, _state, _lat, _lng = _line.split("|")
    CITIES[(_city.lower(), _state)] = (float(_lat), float(_lng))
