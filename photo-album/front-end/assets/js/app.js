(function () {
  var client = apigClientFactory.newClient({ apiKey: window.APP_CONFIG.apiKey });

  var sdkCopy = apiGateway.core.utils.copy;
  apiGateway.core.utils.copy = function (obj) {
    if (obj instanceof Blob || obj instanceof ArrayBuffer || ArrayBuffer.isView(obj)) return obj;
    return sdkCopy(obj);
  };

  function $(id) { return document.getElementById(id); }

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
        cap.textContent = (r.labels || []).join(", ");
        fig.appendChild(img); fig.appendChild(cap); grid.appendChild(fig);
      });
    }).catch(function (err) {
      console.error(err);
      status.textContent = "Search failed. See the browser console.";
    });
  });

  $("upload-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var file = $("file-input").files[0], status = $("upload-status");
    if (!file) { status.textContent = "Choose a photo first."; return; }
    var labels = $("labels-input").value.split(",")
      .map(function (s) { return s.trim(); }).filter(Boolean).join(", ");
    status.textContent = "Uploading...";
    var reader = new FileReader();
    reader.onload = function () {
      var body = new Uint8Array(reader.result);
      var params = {
        "x-object-key": file.name,
        "Content-Type": file.type,
        "x-amz-meta-customLabels": labels
      };
      Promise.resolve().then(function () {
        return client.uploadPut(params, body, {});
      }).then(function () {
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
