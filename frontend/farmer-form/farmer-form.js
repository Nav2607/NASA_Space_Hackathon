"use strict";

const crops = [
  { value: "corn", label: "Corn" },
  { value: "soybean", label: "Soybean" },
  { value: "winter_wheat", label: "Winter wheat" },
  { value: "red_clover", label: "Red clover" },
  { value: "cereal_rye", label: "Cereal rye" }
];

const MAX_YEARS = 4;
const MAX_ROTATION_ROWS = 12;
const MAX_HISTORY_ROWS = 10;

const form = document.getElementById("farmerForm");
const message = document.getElementById("formMessage");

let rotation = [];
let history = [];
let nextRotationId = 1;
let nextHistoryId = 1;

function el(id) {
  return document.getElementById(id);
}

function selectedRadio(name) {
  return document.querySelector(`input[name="${name}"]:checked`)?.value || "unknown";
}

function checkedValues(name) {
  return [...document.querySelectorAll(`input[name="${name}"]:checked`)].map(input => input.value);
}

function readNumber(id) {
  const input = el(id);
  if (!input || input.value.trim() === "") return null;

  const value = Number(input.value);
  return Number.isFinite(value) && value >= 0 ? value : null;
}

function labelForCrop(value) {
  return crops.find(c => c.value === value)?.label || value;
}

function priorityLabel(value) {
  const labels = {
    1: "Low",
    2: "Slight",
    3: "Moderate",
    4: "High",
    5: "Top"
  };
  return labels[value] || "Moderate";
}

function createField(labelText, input) {
  const wrapper = document.createElement("div");
  wrapper.className = "rotation-field";

  const label = document.createElement("label");
  label.textContent = labelText;
  label.htmlFor = input.id;

  wrapper.append(label, input);
  return wrapper;
}

function createCropSelect(id, value, onChange) {
  const select = document.createElement("select");
  select.id = id;

  crops.forEach(crop => {
    const option = document.createElement("option");
    option.value = crop.value;
    option.textContent = crop.label;
    select.appendChild(option);
  });

  select.value = value;
  select.addEventListener("change", () => onChange(select.value));
  return select;
}

function createYearSelect(id, value, onChange) {
  const select = document.createElement("select");
  select.id = id;

  for (let i = 0; i < MAX_YEARS; i++) {
    const option = document.createElement("option");
    option.value = String(i);
    option.textContent = `Year ${i + 1}`;
    select.appendChild(option);
  }

  select.value = String(value);
  select.addEventListener("change", () => onChange(Number(select.value)));
  return select;
}

function buildCropChoices(containerId, name) {
  const container = el(containerId);
  container.innerHTML = "";

  crops.forEach(crop => {
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.name = name;
    input.value = crop.value;
    input.addEventListener("change", updateSummary);
    label.append(input, document.createTextNode(crop.label));
    container.appendChild(label);
  });
}

function parseDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;

  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));

  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) return null;

  return date;
}

function clearMessage() {
  message.className = "";
  message.innerHTML = "";
}

function showErrors(errors) {
  message.className = "error";
  message.innerHTML = `<strong>Please review these inputs:</strong>`;

  const list = document.createElement("ul");
  errors.forEach(text => {
    const li = document.createElement("li");
    li.textContent = text;
    list.appendChild(li);
  });

  message.appendChild(list);
  message.scrollIntoView({ behavior: "smooth", block: "nearest" });
  message.focus({ preventScroll: true });
}

function showSuccess(text) {
  message.className = "success";
  message.innerHTML = `<strong>${text}</strong>`;
}

/* ---------- irrigation ---------- */

function updateIrrigation() {
  const hasIrrigation = selectedRadio("irrigation") === "yes";
  el("irrigationDetails").hidden = !hasIrrigation;
  updateWaterLimit();
  updateSummary();
}

function updateWaterLimit() {
  const showCapacity =
    selectedRadio("irrigation") === "yes" &&
    selectedRadio("waterLimit") === "known";

  el("capacityGroup").hidden = !showCapacity;
  updateSummary();
}

/* ---------- optional blocks ---------- */

function setupOptionalLimit(toggleId, groupId) {
  const toggle = el(toggleId);
  toggle.addEventListener("change", () => {
    el(groupId).hidden = !toggle.checked;
    updateSummary();
  });
}

setupOptionalLimit("enableNitrogen", "nitrogenGroup");
setupOptionalLimit("enableBudget", "budgetGroup");

el("equipmentStatus").addEventListener("change", () => {
  el("equipmentGroup").hidden = el("equipmentStatus").value !== "specified";
  updateSummary();
});

/* ---------- rotation ---------- */

function addRotationRow() {
  if (rotation.length >= MAX_ROTATION_ROWS) return;

  const yearIndex = Math.min(rotation.length, MAX_YEARS - 1);

  rotation.push({
    id: nextRotationId++,
    crop: "corn",
    yearIndex,
    dateMode: "typical",
    start: "",
    end: ""
  });

  renderRotation();
  updateSummary();
}

function updateRotationInfo() {
  const estimatedCount = rotation.filter(r => r.dateMode === "typical").length;
  el("rotationInfo").textContent =
    `${rotation.length} crop entr${rotation.length === 1 ? "y" : "ies"} · ` +
    `${estimatedCount} using typical local dates · maximum horizon: ${MAX_YEARS} years`;
}

function renderRotation() {
  const container = el("rotationRows");
  container.innerHTML = "";

  rotation.forEach((row, index) => {
    const card = document.createElement("div");
    card.className = "rotation-card";

    const header = document.createElement("div");
    header.className = "rotation-card__header";

    const title = document.createElement("div");
    title.className = "rotation-card__title";
    title.textContent = `Crop ${index + 1}`;

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "remove-button";
    remove.textContent = "Remove";
    remove.disabled = rotation.length === 1;
    remove.addEventListener("click", () => {
      rotation = rotation.filter(item => item.id !== row.id);
      renderRotation();
      updateSummary();
    });

    header.append(title, remove);

    const grid = document.createElement("div");
    grid.className = "rotation-card__grid";

    const topRow = document.createElement("div");
    topRow.className = "rotation-row";

    const cropSelect = createCropSelect(
      `rotation-crop-${row.id}`,
      row.crop,
      value => {
        row.crop = value;
        updateSummary();
      }
    );

    const yearSelect = createYearSelect(
      `rotation-year-${row.id}`,
      row.yearIndex,
      value => {
        row.yearIndex = value;
        updateSummary();
      }
    );

    topRow.append(
      createField("Crop", cropSelect),
      createField("Growing year", yearSelect)
    );

    const dateModeSelect = document.createElement("select");
    dateModeSelect.id = `rotation-mode-${row.id}`;

    [
      ["typical", "Use typical local dates"],
      ["manual", "Enter my planting and harvest dates"]
    ].forEach(([value, label]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      dateModeSelect.appendChild(option);
    });

    dateModeSelect.value = row.dateMode;

    const dateRow = document.createElement("div");
    dateRow.className = "rotation-row";

    const startInput = document.createElement("input");
    startInput.type = "date";
    startInput.id = `rotation-start-${row.id}`;
    startInput.value = row.start;
    startInput.addEventListener("change", () => {
      row.start = startInput.value;
      updateSummary();
    });

    const endInput = document.createElement("input");
    endInput.type = "date";
    endInput.id = `rotation-end-${row.id}`;
    endInput.value = row.end;
    endInput.addEventListener("change", () => {
      row.end = endInput.value;
      updateSummary();
    });

    dateRow.append(
      createField("Planting date", startInput),
      createField("Harvest / end date", endInput)
    );

    const note = document.createElement("div");
    note.className = "rotation-note";
    note.textContent =
      "Typical local dates will be estimated from regional crop calendars during comparison.";

    function updateMode() {
      row.dateMode = dateModeSelect.value;
      dateRow.hidden = row.dateMode !== "manual";
      note.hidden = row.dateMode !== "typical";
      updateRotationInfo();
      updateSummary();
    }

    dateModeSelect.addEventListener("change", updateMode);

    grid.append(
      topRow,
      createField("Planting schedule", dateModeSelect),
      dateRow,
      note
    );

    card.append(header, grid);
    container.appendChild(card);

    updateMode();
  });

  el("addCrop").disabled = rotation.length >= MAX_ROTATION_ROWS;
  updateRotationInfo();
}

function getRotationErrors() {
  const errors = [];
  const firstYear = Number(el("rotationStartYear").value);

  if (!Number.isInteger(firstYear) || firstYear < 2000 || firstYear > 2100) {
    errors.push("Enter a valid first growing year (2000–2100).");
    return errors;
  }

  const horizonStart = Date.UTC(firstYear, 0, 1);
  const horizonEnd = Date.UTC(firstYear + MAX_YEARS, 0, 1);

  rotation.forEach((row, index) => {
    const cropNo = index + 1;

    if (row.dateMode === "typical") return;

    if (!row.start || !row.end) {
      errors.push(`Crop ${cropNo}: enter both dates, or use typical local dates.`);
      return;
    }

    const start = parseDate(row.start);
    const end = parseDate(row.end);

    if (!start || !end) {
      errors.push(`Crop ${cropNo}: enter valid calendar dates.`);
      return;
    }

    if (end <= start) {
      errors.push(`Crop ${cropNo}: harvest must be after planting.`);
      return;
    }

    if (start.getTime() < horizonStart || end.getTime() >= horizonEnd) {
      errors.push(
        `Crop ${cropNo}: dates must fit within the 4-year planning period (${firstYear}–${firstYear + 3}).`
      );
    }

    const selectedYear = firstYear + row.yearIndex;
    if (start.getUTCFullYear() !== selectedYear) {
      errors.push(
        `Crop ${cropNo}: planting date must match the selected growing year (${selectedYear}).`
      );
    }
  });

  return errors;
}

/* ---------- history ---------- */

function addHistoryRow() {
  if (history.length >= MAX_HISTORY_ROWS) return;

  history.push({
    id: nextHistoryId++,
    year: new Date().getFullYear() - 1,
    crop: "corn"
  });

  renderHistory();
  updateSummary();
}

function renderHistory() {
  const container = el("historyRows");
  container.innerHTML = "";

  history.forEach(row => {
    const card = document.createElement("div");
    card.className = "history-card";

    const yearWrap = document.createElement("div");
    yearWrap.className = "rotation-field";
    const yearLabel = document.createElement("label");
    yearLabel.textContent = "Year";
    yearLabel.htmlFor = `history-year-${row.id}`;
    const yearInput = document.createElement("input");
    yearInput.type = "number";
    yearInput.id = `history-year-${row.id}`;
    yearInput.min = "1900";
    yearInput.max = String(new Date().getFullYear());
    yearInput.value = row.year;
    yearInput.addEventListener("input", () => {
      row.year = yearInput.value;
      updateSummary();
    });
    yearWrap.append(yearLabel, yearInput);

    const cropWrap = document.createElement("div");
    cropWrap.className = "rotation-field";
    const cropLabel = document.createElement("label");
    cropLabel.textContent = "Crop grown";
    cropLabel.htmlFor = `history-crop-${row.id}`;
    const cropSelect = createCropSelect(
      `history-crop-${row.id}`,
      row.crop,
      value => {
        row.crop = value;
        updateSummary();
      }
    );
    cropWrap.append(cropLabel, cropSelect);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "remove-button";
    remove.textContent = "Remove";
    remove.addEventListener("click", () => {
      history = history.filter(item => item.id !== row.id);
      renderHistory();
      updateSummary();
    });

    card.append(yearWrap, cropWrap, remove);
    container.appendChild(card);
  });

  el("addHistory").disabled = history.length >= MAX_HISTORY_ROWS;
}

/* ---------- priorities ---------- */

[
  ["waterPriority", "waterValue"],
  ["nitrogenPriority", "nitrogenValue"],
  ["soilPriority", "soilValue"],
  ["weatherPriority", "weatherValue"]
].forEach(([inputId, outputId]) => {
  el(inputId).addEventListener("input", event => {
    const value = Number(event.target.value);
    el(outputId).textContent = `${value} / 5 · ${priorityLabel(value)}`;
    updateSummary();
  });
});

/* ---------- summary ---------- */

function friendlySoil(value) {
  const map = {
    unknown: "Unknown",
    sandy: "Sandy",
    sandy_loam: "Sandy loam",
    loam: "Loam",
    silt_loam: "Silt loam",
    clay_loam: "Clay loam",
    clay: "Clay"
  };
  return map[value] || "Unknown";
}

function friendlyIrrigation() {
  const irrigation = selectedRadio("irrigation");

  if (irrigation === "no") return "No irrigation";
  if (irrigation === "unknown") return "Unknown";
  if (irrigation === "yes") {
    const limit = selectedRadio("waterLimit");
    if (limit === "known") {
      const amount = readNumber("capacity");
      const unit = el("capacityUnit").value === "mm_per_season"
        ? "mm/season"
        : "m³/ha/season";

      return amount !== null ? `Yes · ${amount} ${unit}` : "Yes · limit known";
    }
    if (limit === "unknown") return "Yes · limit unknown";
    if (limit === "unspecified") return "Yes · no specified limit";
  }

  return "Unknown";
}

function computeMainPriority() {
  const priorities = [
    { key: "Water", value: Number(el("waterPriority").value) },
    { key: "Nitrogen", value: Number(el("nitrogenPriority").value) },
    { key: "Soil", value: Number(el("soilPriority").value) },
    { key: "Weather", value: Number(el("weatherPriority").value) }
  ];

  priorities.sort((a, b) => b.value - a.value);

  if (priorities[0].value === priorities[1].value) return "Balanced";
  return priorities[0].key;
}

function computeConstraints() {
  const constraints = [];

  if (el("enableNitrogen").checked) constraints.push("Nitrogen");
  if (el("enableBudget").checked) constraints.push("Budget");

  const mustGrow = checkedValues("mustGrow");
  const avoid = checkedValues("avoid");

  if (mustGrow.length) constraints.push("Required crops");
  if (avoid.length) constraints.push("Avoid list");

  return constraints.length ? constraints.join(", ") : "None set";
}

function updateSummary() {
  el("summarySoil").textContent = friendlySoil(el("soil").value);
  el("summaryIrrigation").textContent = friendlyIrrigation();
  el("summaryRotationCount").textContent =
    `${rotation.length} ${rotation.length === 1 ? "crop" : "crops"}`;
  el("summaryPriority").textContent = computeMainPriority();
  el("summaryConstraints").textContent = computeConstraints();
  el("summaryHorizon").textContent = `${MAX_YEARS} years max`;

  const firstYearValid =
    Number.isInteger(Number(el("rotationStartYear").value)) &&
    Number(el("rotationStartYear").value) >= 2000 &&
    Number(el("rotationStartYear").value) <= 2100;

  const hasRotation = rotation.length > 0;
  const hasBasicSoil = el("soil").value !== "";
  const ready = firstYearValid && hasRotation && hasBasicSoil;

  const statusBox = el("statusBox");
  const statusText = el("statusText");

  if (ready) {
    statusBox.classList.add("status-box--ready");
    statusText.textContent = "Farm details look ready for comparison";
  } else {
    statusBox.classList.remove("status-box--ready");
    statusText.textContent = "Still missing a few details";
  }
}

/* ---------- validation helpers ---------- */

function optionalLimit(toggleId, inputId, label, errors) {
  if (!el(toggleId).checked) return null;

  const value = readNumber(inputId);
  if (value === null) errors.push(`Enter a valid ${label}.`);
  return value;
}

/* ---------- submit ---------- */

form.addEventListener("submit", event => {
  event.preventDefault();
  clearMessage();

  const errors = [];
  errors.push(...getRotationErrors());

  const irrigation = selectedRadio("irrigation");
  const waterLimit = irrigation === "yes"
    ? selectedRadio("waterLimit")
    : "not_applicable";

  const capacityKnown = irrigation === "yes" && waterLimit === "known";
  const enteredCapacity = capacityKnown ? readNumber("capacity") : null;

  if (capacityKnown && enteredCapacity === null) {
    errors.push("Enter a valid irrigation water limit.");
  }

  const capacityUnit = el("capacityUnit").value;
  const capacityMm =
    enteredCapacity === null
      ? null
      : capacityUnit === "m3_per_ha_per_season"
        ? enteredCapacity / 10
        : enteredCapacity;

  const mustGrow = checkedValues("mustGrow");
  const avoid = checkedValues("avoid");

  const overlaps = mustGrow.filter(c => avoid.includes(c));
  if (overlaps.length) {
    errors.push(`A crop cannot be both required and avoided: ${overlaps.join(", ")}.`);
  }

  const nitrogenLimit = optionalLimit(
    "enableNitrogen",
    "nitrogenLimit",
    "nitrogen fertilizer limit",
    errors
  );

  const budgetLimit = optionalLimit(
    "enableBudget",
    "budget",
    "annual operating budget",
    errors
  );

  const equipmentSpecified = el("equipmentStatus").value === "specified";
  const equipment = checkedValues("equipment");

  if (equipmentSpecified && equipment.length === 0) {
    errors.push("Select available equipment, or leave equipment as not specified.");
  }

  const usedYears = new Set();
  history.forEach((row, index) => {
    const year = Number(row.year);

    if (!Number.isInteger(year) || year < 1900 || year > new Date().getFullYear()) {
      errors.push(`Past crop ${index + 1}: enter a valid year.`);
    }

    if (usedYears.has(year)) {
      errors.push(`Past crop history year ${year} appears more than once.`);
    }

    usedYears.add(year);
  });

  if (errors.length) {
    if (
      overlaps.length ||
      equipmentSpecified ||
      el("enableNitrogen").checked ||
      el("enableBudget").checked
    ) {
      el("advancedOptions").open = true;
    }

    if (history.length) {
      el("historyDetails").open = true;
    }

    showErrors(errors);
    return;
  }

  const firstYear = Number(el("rotationStartYear").value);

  const currentRotation = rotation.map((row, index) => {
    const usesTypicalDates = row.dateMode === "typical";

    return {
      sequence: index + 1,
      growingYear: firstYear + row.yearIndex,
      crop: row.crop,
      dateSource: usesTypicalDates ? "regional_calendar_pending" : "farmer_provided",
      plantingDate: usesTypicalDates ? null : row.start,
      harvestDate: usesTypicalDates ? null : row.end
    };
  }).sort((a, b) => a.growingYear - b.growingYear || a.sequence - b.sequence);

  const farmData = {
    soilTexture: el("soil").value,
    drainage: el("drainage").value,
    slope: el("slope").value,

    irrigation: {
      availability: irrigation,
      limitStatus: waterLimit,
      capacityKnown,
      capacityMm,
      originalAmount: enteredCapacity,
      originalUnit: capacityKnown ? capacityUnit : null
    },

    planning: {
      firstYear,
      horizonYears: MAX_YEARS,
      needsCalendarResolution: currentRotation.some(
        row => row.dateSource === "regional_calendar_pending"
      )
    },

    currentRotation,

    cropHistory: history.map(row => ({
      year: Number(row.year),
      crop: row.crop,
      source: "farmer_reported"
    })),

    mustGrow,
    avoid,

    equipment: {
      specified: equipmentSpecified,
      available: equipmentSpecified ? equipment : []
    },

    constraints: {
      nitrogenLimitKgHaYear: nitrogenLimit,
      budgetCadHaYear: budgetLimit
    },

    priorities: {
      water: Number(el("waterPriority").value),
      nitrogen: Number(el("nitrogenPriority").value),
      soilCover: Number(el("soilPriority").value),
      weatherRisk: Number(el("weatherPriority").value)
    }
  };

  window.terraShiftFarmData = farmData;

  console.log("TerraShift Farmer Input:");
  console.log(JSON.stringify(farmData, null, 2));

  window.dispatchEvent(
    new CustomEvent("terrashift:compare", { detail: farmData })
  );

  showSuccess(
    farmData.planning.needsCalendarResolution
      ? "Your inputs are saved. Typical local crop dates still need to be resolved during comparison."
      : "Your inputs are saved and ready for comparison."
  );
});

/* ---------- listeners ---------- */

document.querySelectorAll('input[name="irrigation"]').forEach(input => {
  input.addEventListener("change", updateIrrigation);
});

document.querySelectorAll('input[name="waterLimit"]').forEach(input => {
  input.addEventListener("change", updateWaterLimit);
});

[
  "soil",
  "drainage",
  "slope",
  "rotationStartYear",
  "capacity",
  "capacityUnit",
  "nitrogenLimit",
  "budget"
].forEach(id => {
  const node = el(id);
  if (node) node.addEventListener("input", updateSummary);
  if (node) node.addEventListener("change", updateSummary);
});

el("addCrop").addEventListener("click", addRotationRow);
el("addHistory").addEventListener("click", addHistoryRow);

/* ---------- init ---------- */

buildCropChoices("mustGrowOptions", "mustGrow");
buildCropChoices("avoidOptions", "avoid");

addRotationRow();
renderHistory();
updateIrrigation();

el("waterValue").textContent = `3 / 5 · ${priorityLabel(3)}`;
el("nitrogenValue").textContent = `3 / 5 · ${priorityLabel(3)}`;
el("soilValue").textContent = `3 / 5 · ${priorityLabel(3)}`;
el("weatherValue").textContent = `3 / 5 · ${priorityLabel(3)}`;

updateSummary();