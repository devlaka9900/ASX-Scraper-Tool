// Review Helper — visual audit only, no UI panel

document.addEventListener("DOMContentLoaded", function () {

    const style = document.createElement("style");
    style.textContent = `
        .rh { outline: 2px solid transparent; outline-offset: 2px; position: relative; }
        .rh-green    { outline-color: #28a745; background: rgba(212,237,218,.45); }
        .rh-red      { outline-color: #dc3545; background: rgba(255,204,204,.55); }
        .rh-orange   { outline-color: #fd7e14; background: rgba(255,243,205,.55); }
        .rh-dark-red { outline: 3px solid #721c24; background: rgba(248,215,218,.65); }
        .rh-grey     { outline-color: #868e96; background: rgba(233,236,239,.45); }
        .rh-blue     { outline-color: #0066cc; background: rgba(204,229,255,.45); }
        .rh-purple   { outline-color: #6f42c1; background: rgba(232,213,245,.45); }
        .rh-badge {
            display: inline-block;
            font: 700 9px/1 monospace;
            padding: 1px 5px;
            border-radius: 3px;
            color: #fff;
            background: #555;
            margin-right: 5px;
            vertical-align: middle;
            user-select: none;
            pointer-events: none;
        }
        img.rh-img { outline: 3px solid #0066cc; }
        .rh-img-badge {
            position: absolute; top: 2px; left: 2px;
            font: 700 9px/1 monospace;
            background: #0066cc; color: #fff;
            padding: 1px 5px; border-radius: 3px;
            pointer-events: none;
        }
        .rh-img-wrap { position: relative; display: inline-block; }
    `;
    document.head.appendChild(style);

    function badge(el, text, bg) {
        const b = document.createElement("span");
        b.className = "rh-badge";
        b.style.background = bg || "#555";
        b.textContent = text;
        el.insertBefore(b, el.firstChild);
    }

    const VALID_END = [".", ";", "—", ":", ")", '"', "”", "!", "?", "]"];

    function chunk(list, fn) {
        const arr = Array.from(list);
        let i = 0;
        (function step() {
            const end = Math.min(i + 80, arr.length);
            while (i < end) fn(arr[i++]);
            if (i < arr.length) setTimeout(step, 0);
        })();
    }

    // Paragraphs
    chunk(document.querySelectorAll("p"), function (el) {
        const text = el.textContent.trim();
        if (!text) {
            el.classList.add("rh", "rh-orange");
            badge(el, "EMPTY", "#fd7e14");
        } else if (/�/.test(text)) {
            el.classList.add("rh", "rh-dark-red");
            badge(el, "ENC ERR", "#721c24");
        } else if (!VALID_END.some(s => text.endsWith(s))) {
            el.classList.add("rh", "rh-red");
            badge(el, "P✗", "#dc3545");
        } else {
            el.classList.add("rh", "rh-green");
            badge(el, "P✓", "#28a745");
        }
    });

    // Headings
    chunk(document.querySelectorAll("h1,h2,h3,h4,h5,h6"), function (el) {
        el.classList.add("rh", "rh-grey");
        badge(el, el.tagName, "#495057");
    });

    // Tables
    chunk(document.querySelectorAll("table"), function (el) {
        el.classList.add("rh", "rh-blue");
        const rows = el.querySelectorAll("tr").length;
        const fr = el.querySelector("tr");
        const cols = fr ? fr.querySelectorAll("td,th").length : 0;
        badge(el, "TABLE " + rows + "r\xD7" + cols + "c", "#0066cc");
    });

    // Lists (top-level only)
    chunk(document.querySelectorAll("ul, ol"), function (el) {
        if (el.closest("ul, ol")) return;
        el.classList.add("rh", "rh-purple");
        badge(el, el.tagName + " " + el.querySelectorAll("li").length, "#6f42c1");
    });

    // Images
    let imgN = 0;
    chunk(document.querySelectorAll("img"), function (img) {
        imgN++;
        img.classList.add("rh-img");
        const wrap = document.createElement("span");
        wrap.className = "rh-img-wrap";
        img.parentNode.insertBefore(wrap, img);
        wrap.appendChild(img);
        const b = document.createElement("span");
        b.className = "rh-img-badge";
        b.textContent = "IMG " + imgN;
        wrap.appendChild(b);
    });

    // Footnotes — check each div.footnote[id] has an href reference above it
    setTimeout(function () {
        const linked = new Set();
        document.querySelectorAll("a[href^=\"#\"]").forEach(function (a) {
            linked.add(a.getAttribute("href").slice(1));
        });

        document.querySelectorAll("div.footnote[id]").forEach(function (el) {
            if (linked.has(el.id)) {
                el.classList.add("rh", "rh-green");
                badge(el, "FN ✓", "#28a745");
            } else {
                el.classList.add("rh", "rh-dark-red");
                badge(el, "FN NO REF ⚠", "#721c24");
            }
        });
    }, 0);

});
