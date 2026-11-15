(function () {
  var client = apigClientFactory.newClient({ apiKey: window.APP_CONFIG.apiKey });

  function $(id) { return document.getElementById(id); }

  // ---------- Search: GET /search?q=... ----------
  $("search-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var q = $("search-input").value.trim();
    var status = $("search-status"), grid = $("results");
    grid.innerHTML = "";
    if (!q) { status.textContent = "Type something to search."; return; }
    status.textContent = "Searching...";
    client.searchGet({ q: q }, {}, {}).then(function (res) {
      var results = (res.data && res.data.results) || [];
      status.textContent = results.length ? results.length + " photo(s) found" : "No photos found.";
      results.forEach(function (r) {
        var fig = document.createElement("figure");
        var img = document.createElement("img");
        img.src = r.url; img.alt = (r.labels || []).join(", ");
        var cap = document.createElement("figcaption");
        cap.textContent = (r.labels || []).join(", ");   // textContent: no HTML injection
        fig.appendChild(img); fig.appendChild(cap); grid.appendChild(fig);
      });
    }).catch(function (err) {
      console.error(err);
      status.textContent = "Search failed. See the browser console.";
    });
  });

  // ---------- Upload: PUT /upload with x-object-key (file name) and x-amz-meta-customLabels ----------
  $("upload-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var file = $("file-input").files[0], status = $("upload-status");
    if (!file) { status.textContent = "Choose a photo first."; return; }
    var labels = $("labels-input").value.split(",")
      .map(function (s) { return s.trim(); }).filter(Boolean).join(", ");
    status.textContent = "Uploading...";
    var reader = new FileReader();
    reader.onload = function () {
      // Uint8Array, not File/ArrayBuffer: the generated SDK drops bodies that have no enumerable keys.
      var body = new Uint8Array(reader.result);
      var headers = { "Content-Type": file.type, "x-object-key": file.name };
      if (labels) headers["x-amz-meta-customLabels"] = labels;
      client.uploadPut({}, body, { headers: headers }).then(function () {
        status.textContent = "Uploaded " + file.name + (labels ? " with labels: " + labels : "") +
          ". It can take a few seconds to be searchable.";
        $("upload-form").reset();
      }).catch(function (err) {
        console.error(err);
        status.textContent = "Upload failed. See the browser console.";
      });
    };
    reader.readAsArrayBuffer(file);
  });
})();
