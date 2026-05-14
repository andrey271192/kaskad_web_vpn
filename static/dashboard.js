(function () {
  const cred = { credentials: "same-origin" };

  function api(path, opts) {
    return fetch(path, Object.assign({}, cred, opts)).then(function (res) {
      if (res.status === 401) {
        window.location.reload();
        throw new Error("401");
      }
      return res;
    });
  }

  function pill(active) {
    var s = (active || "").toLowerCase();
    var cls = "pill";
    if (s === "active") cls += " pill-active";
    else if (s === "inactive" || s === "missing") cls += " pill-muted";
    return '<span class="' + cls + '">' + escapeHtml(active || "—") + "</span>";
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderSystem(data) {
    var g = document.getElementById("system-grid");
    var cells = [
      ["MachineId", data.machine_id],
      ["Uptime", data.uptime],
      ["Load", data.load],
      ["Mem", data.mem],
      ["IPADDR / IPv4", String(data.ipaddrs || "").replace(/\n/g, "<br>")],
      ["yaskad", data.yaskad_version],
      ["BOT_TOKEN", data.bot_token_masked],
      ["BOT_CHAT_ID", data.bot_chat_masked],
    ];
    g.innerHTML = cells
      .map(function (kv) {
        return (
          '<div class="sys-cell"><span class="sys-k">' +
          escapeHtml(kv[0]) +
          '</span><span class="sys-v">' +
          kv[1] +
          "</span></div>"
        );
      })
      .join("");
  }

  function renderServices(rows) {
    var tb = document.querySelector("#tbl-services tbody");
    tb.innerHTML = (rows || [])
      .map(function (r) {
        return (
          "<tr><td class=\"mono\">" +
          escapeHtml(r.unit) +
          "</td><td>" +
          pill(r.active) +
          "</td><td>" +
          escapeHtml(r.enabled) +
          "</td></tr>"
        );
      })
      .join("");
  }

  function renderClients(list) {
    var tb = document.querySelector("#tbl-clients tbody");
    tb.innerHTML = (list || [])
      .map(function (c) {
        return (
          "<tr data-id=\"" +
          escapeHtml(c.id) +
          "\"><td>" +
          escapeHtml(c.user) +
          "</td><td class=\"mono\">" +
          escapeHtml(c.proto) +
          "</td><td class=\"mono\">" +
          escapeHtml(String(c.in_port)) +
          '</td><td class="arrow-cell">→</td><td class="mono">' +
          escapeHtml(c.target) +
          "</td><td class=\"mono\">" +
          escapeHtml(String(c.out_port)) +
          "</td><td>" +
          escapeHtml(c.note || "") +
          "</td><td>" +
          escapeHtml(c.where || "") +
          '</td><td class="row-actions"><button type="button" class="icon-btn edit" title="Изменить">✎</button> <button type="button" class="icon-btn del" title="Удалить">✕</button></td></tr>'
        );
      })
      .join("");

    tb.querySelectorAll("tr").forEach(function (row) {
      var id = row.getAttribute("data-id");
      row.querySelector(".edit").addEventListener("click", function () {
        openModalEdit(id);
      });
      row.querySelector(".del").addEventListener("click", function () {
        if (!confirm("Удалить правило?")) return;
        api("/api/clients/" + encodeURIComponent(id), { method: "DELETE" })
          .then(function (r) {
            return r.json();
          })
          .then(function () {
            loadClients();
          })
          .catch(function () {});
      });
    });
  }

  function loadSystem() {
    return api("/api/system")
      .then(function (r) {
        return r.json();
      })
      .then(renderSystem);
  }

  function loadServices() {
    return api("/api/services")
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        renderServices(d.services);
      });
  }

  function loadClients() {
    return api("/api/clients")
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        renderClients(d.clients);
      });
  }

  function loadAll() {
    return Promise.all([loadSystem(), loadServices(), loadClients()]).catch(function (e) {
      console.warn(e);
    });
  }

  var overlay = document.getElementById("modal-overlay");
  var form = document.getElementById("form-client");

  function openModalNew() {
    document.getElementById("modal-title").textContent = "Новый клиент";
    form.reset();
    document.getElementById("f-id").value = "";
    overlay.hidden = false;
  }

  function openModalEdit(id) {
    api("/api/clients")
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        var c = (d.clients || []).find(function (x) {
          return x.id === id;
        });
        if (!c) return;
        document.getElementById("modal-title").textContent = "Изменить клиента";
        document.getElementById("f-id").value = c.id;
        document.getElementById("f-user").value = c.user;
        document.getElementById("f-proto").value = c.proto;
        document.getElementById("f-in").value = c.in_port;
        document.getElementById("f-target").value = c.target;
        document.getElementById("f-out").value = c.out_port;
        document.getElementById("f-note").value = c.note || "";
        document.getElementById("f-where").value = c.where || "";
        overlay.hidden = false;
      });
  }

  function closeModal() {
    overlay.hidden = true;
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var fd = new FormData(form);
    var body = {
      user: fd.get("user"),
      proto: fd.get("proto"),
      in_port: parseInt(fd.get("in_port"), 10),
      target: fd.get("target"),
      out_port: parseInt(fd.get("out_port"), 10),
      note: fd.get("note") || "",
      where: fd.get("where") || "",
    };
    var cid = (fd.get("id") || "").toString().trim();
    var url = cid ? "/api/clients/" + encodeURIComponent(cid) : "/api/clients";
    var method = cid ? "PUT" : "POST";
    api(url, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (r) {
        return r.json().then(function (j) {
          if (!r.ok) throw new Error(j.error || r.status);
          return j;
        });
      })
      .then(function () {
        closeModal();
        loadClients();
      })
      .catch(function (e) {
        alert(e.message || String(e));
      });
  });

  document.getElementById("modal-cancel").addEventListener("click", closeModal);
  overlay.addEventListener("click", function (ev) {
    if (ev.target === overlay) closeModal();
  });

  document.getElementById("btn-add-client").addEventListener("click", openModalNew);
  document.getElementById("btn-refresh").addEventListener("click", loadAll);

  document.getElementById("btn-load-iptables").addEventListener("click", function () {
    api("/api/iptables/raw")
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        document.getElementById("iptables-out").textContent = d.raw || "";
      });
  });

  loadAll();
})();
