Put the API Gateway generated JavaScript SDK (SDK1) here.

API Gateway -> APIs -> <your API> -> Stages -> <stage> -> Stage actions -> Generate SDK -> JavaScript.
Unzip, then copy apigClient.js and the lib/ folder into this directory.
apigClient.js is specific to your API, so it is intentionally not in this repo until you generate it.

app.js expects these generated methods: searchGet(...) and uploadPut(...).
If your SDK names them differently, open apigClient.js and adjust the two calls in app.js.
