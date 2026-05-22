(function (global) {
  "use strict";

  function normalize(value) {
    return (value || "").toString().trim().toLowerCase();
  }

  function initServerSidebarSearch(root) {
    var container = root || document.getElementById("server-sidebar");
    if (!container) return;

    var input = container.querySelector("#server-sidebar-search");
    var emptyHint = container.querySelector("#sidebar-search-empty");
    var searchableItems = container.querySelectorAll("[data-sidebar-search]");
    var sections = container.querySelectorAll("[data-sidebar-section]");

    if (!input || !searchableItems.length) return;

    function applyFilter() {
      var term = normalize(input.value);
      var visibleCount = 0;

      searchableItems.forEach(function (el) {
        var haystack = normalize(el.getAttribute("data-sidebar-search"));
        var match = !term || haystack.indexOf(term) !== -1;
        el.classList.toggle("d-none", !match);
        if (match) visibleCount += 1;
      });

      sections.forEach(function (section) {
        var visibleInSection = section.querySelectorAll(
          "[data-sidebar-search]:not(.d-none)",
        ).length;
        section.classList.toggle("d-none", term.length > 0 && visibleInSection === 0);
      });

      if (emptyHint) {
        emptyHint.classList.toggle("d-none", !term || visibleCount > 0);
      }
    }

    input.addEventListener("input", applyFilter);
    input.addEventListener("search", applyFilter);
  }

  global.initServerSidebarSearch = initServerSidebarSearch;

  document.addEventListener("DOMContentLoaded", function () {
    initServerSidebarSearch(document.getElementById("server-sidebar"));
  });
})(window);
