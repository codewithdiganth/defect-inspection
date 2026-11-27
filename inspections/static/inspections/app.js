(() => {
  const csrfToken = () =>
    document.cookie
      .split("; ")
      .find((cookie) => cookie.startsWith("csrftoken="))
      ?.split("=")
      .slice(1)
      .join("=") || "";

  const escapeHtml = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[character]);

  const apiRequest = async (url, options = {}) => {
    const response = await fetch(url, {
      credentials: "same-origin",
      ...options,
      headers: {
        ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        "X-CSRFToken": csrfToken(),
        ...options.headers,
      },
    });
    const contentType = response.headers.get("content-type") || "";
    const body = contentType.includes("application/json")
      ? await response.json()
      : await response.text();
    if (!response.ok) {
      const validationMessage = body && typeof body === "object"
        ? Object.entries(body)
          .map(([field, messages]) => `${field}: ${Array.isArray(messages) ? messages.join(" ") : messages}`)
          .join(" ")
        : "";
      throw new Error(body?.detail || validationMessage || `Request failed (${response.status})`);
    }
    return body;
  };

  const showAlert = (element, message, kind = "danger") => {
    if (!element) return;
    element.className = `alert alert-${kind}`;
    element.textContent = message;
  };

  const statusBadge = (status) => {
    const classes = {
      queued: "text-bg-secondary",
      processing: "text-bg-info",
      completed: "text-bg-success",
      failed: "text-bg-danger",
    };
    return `<span class="badge status-badge ${classes[status] || "text-bg-secondary"}">${escapeHtml(status)}</span>`;
  };

  const formatPercent = (value) =>
    typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "—";

  const uploadForm = document.querySelector("#inspection-upload-form");
  if (uploadForm) {
    const fileInput = document.querySelector("#inspection-files");
    const preview = document.querySelector("#image-preview");
    const alertBox = document.querySelector("#upload-alert");
    const submitButton = document.querySelector("#upload-submit");
    let previewUrls = [];

    fileInput.addEventListener("change", () => {
      previewUrls.forEach(URL.revokeObjectURL);
      previewUrls = [];
      const files = Array.from(fileInput.files || []);
      if (!files.length) {
        preview.innerHTML = '<p class="text-secondary mb-0">No images selected.</p>';
        return;
      }
      preview.innerHTML = files.map((file) => {
        const url = URL.createObjectURL(file);
        previewUrls.push(url);
        return `<div class="preview-tile"><img src="${url}" alt=""><span class="filename small mt-1" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</span><span class="small text-secondary">${(file.size / 1024 / 1024).toFixed(2)} MiB</span></div>`;
      }).join("");
    });

    uploadForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      alertBox.className = "alert d-none";
      const files = Array.from(fileInput.files || []);
      if (!files.length || files.length > 10) {
        showAlert(alertBox, "Choose between 1 and 10 image files.");
        return;
      }
      const formData = new FormData();
      formData.append("product_id", document.querySelector("#product-id").value);
      files.forEach((file) => formData.append("files", file));
      submitButton.disabled = true;
      submitButton.textContent = "Uploading…";
      try {
        const result = await apiRequest(uploadForm.dataset.uploadUrl, {
          method: "POST",
          body: formData,
        });
        window.location.assign(uploadForm.dataset.batchUrlTemplate.replace("{id}", result.id));
      } catch (error) {
        showAlert(alertBox, error.message);
      } finally {
        submitButton.disabled = false;
        submitButton.textContent = "Upload and inspect";
      }
    });
  }

  const batchBody = document.querySelector("#batch-results");
  if (batchBody) {
    let timer;
    const poll = async () => {
      try {
        const batch = await apiRequest(batchBody.dataset.apiUrl);
        batchBody.innerHTML = batch.inspections.map((inspection) => {
          const image = inspection.image_url
            ? `<img class="inspection-thumbnail" src="${escapeHtml(inspection.image_url)}" alt="">`
            : "—";
          return `<tr>
            <td>${image}</td>
            <td>${escapeHtml(inspection.original_filename)}</td>
            <td>${statusBadge(inspection.status)}</td>
            <td>${escapeHtml(inspection.predicted_class || "—")}</td>
            <td>${formatPercent(inspection.confidence)}</td>
            <td>${formatPercent(inspection.defect_probability)}</td>
            <td class="small text-danger">${escapeHtml(inspection.error_message || "—")}</td>
          </tr>`;
        }).join("");
        const pending = batch.inspections.some((item) => ["queued", "processing"].includes(item.status));
        if (!pending) {
          window.clearInterval(timer);
          document.querySelector("#batch-poll-status").textContent = "All items have finished processing.";
        }
      } catch (error) {
        window.clearInterval(timer);
        batchBody.innerHTML = `<tr><td colspan="7" class="text-danger p-3">${escapeHtml(error.message)}</td></tr>`;
      }
    };
    poll();
    timer = window.setInterval(poll, 1500);
  }

  const historyForm = document.querySelector("#history-filters");
  if (historyForm) {
    const results = document.querySelector("#history-results");
    const alertBox = document.querySelector("#history-alert");
    const pageLabel = document.querySelector("#history-page-label");
    const previous = document.querySelector("#history-previous");
    const next = document.querySelector("#history-next");
    const supervisor = Boolean(document.querySelector("#review-modal"));
    let currentUrl = historyForm.dataset.apiUrl;
    const renderHistory = (data) => {
      if (!data.results.length) {
        results.innerHTML = '<tr><td colspan="10" class="text-center text-secondary py-4">No inspections found.</td></tr>';
      } else {
        results.innerHTML = data.results.map((item) => {
          const review = item.review_status === "reviewed"
            ? '<span class="badge text-bg-primary">Reviewed</span>'
            : '<span class="badge text-bg-light border text-dark">Pending</span>';
          const image = item.image_url
            ? `<img class="inspection-thumbnail" src="${escapeHtml(item.image_url)}" alt="">`
            : "—";
          const detailLink = `/inspections/${item.id}/`;
          const reviewButton = supervisor && item.status === "completed"
            ? `<button class="btn btn-sm btn-outline-primary review-action" type="button" data-id="${item.id}" data-prediction="${escapeHtml(item.review?.reviewed_class || item.predicted_class || "Normal")}" data-comment="${escapeHtml(item.review?.comment || "")}">${item.review_status === "reviewed" ? "Edit review" : "Review"}</button>`
            : "";
          return `<tr>
            <td>${image}</td>
            <td><span class="fw-semibold">${escapeHtml(item.product_name)}</span><span class="d-block small text-secondary">${escapeHtml(item.product_id)}</span></td>
            <td><a href="${detailLink}">${escapeHtml(item.predicted_class || item.status)}</a></td>
            <td>${formatPercent(item.confidence)}</td>
            <td>${escapeHtml(item.review?.reviewed_class || "—")}</td>
            <td>${review}</td>
            <td>${escapeHtml(item.reviewer || "—")}</td>
            <td>${escapeHtml(item.submitted_by)}</td>
            <td class="text-nowrap">${new Date(item.created_at).toLocaleString()}</td>
            <td class="text-nowrap">${reviewButton}</td>
          </tr>`;
        }).join("");
      }
      const page = new URL(currentUrl, window.location.origin).searchParams.get("page") || 1;
      pageLabel.textContent = `Page ${page} · ${data.count} inspections`;
      previous.disabled = !data.previous;
      next.disabled = !data.next;
      previous.dataset.url = data.previous || "";
      next.dataset.url = data.next || "";
    };
    const loadHistory = async (url) => {
      alertBox.className = "alert d-none";
      try {
        currentUrl = url;
        const data = await apiRequest(url);
        renderHistory(data);
      } catch (error) {
        showAlert(alertBox, error.message);
      }
    };
    const filteredUrl = () => {
      const url = new URL(historyForm.dataset.apiUrl, window.location.origin);
      new FormData(historyForm).forEach((value, key) => {
        if (value) url.searchParams.set(key, value);
      });
      return url.toString();
    };
    historyForm.addEventListener("submit", (event) => {
      event.preventDefault();
      loadHistory(filteredUrl());
    });
    historyForm.addEventListener("reset", () => window.setTimeout(() => loadHistory(filteredUrl()), 0));
    previous.addEventListener("click", () => previous.dataset.url && loadHistory(previous.dataset.url));
    next.addEventListener("click", () => next.dataset.url && loadHistory(next.dataset.url));

    results.addEventListener("click", (event) => {
      const button = event.target.closest(".review-action");
      if (!button) return;
      document.querySelector("#review-inspection-id").value = button.dataset.id;
      document.querySelector("#reviewed-class").value = button.dataset.prediction;
      document.querySelector("#review-comment").value = button.dataset.comment;
      document.querySelector("#review-alert").classList.add("d-none");
      bootstrap.Modal.getOrCreateInstance(document.querySelector("#review-modal")).show();
    });

    const reviewForm = document.querySelector("#review-form");
    if (reviewForm) {
      reviewForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const id = document.querySelector("#review-inspection-id").value;
        const alert = document.querySelector("#review-alert");
        try {
          await apiRequest(`/api/inspections/${id}/review/`, {
            method: "POST",
            body: JSON.stringify({
              reviewed_class: document.querySelector("#reviewed-class").value,
              comment: document.querySelector("#review-comment").value,
            }),
          });
          bootstrap.Modal.getInstance(document.querySelector("#review-modal")).hide();
          await loadHistory(filteredUrl());
        } catch (error) {
          showAlert(alert, error.message);
        }
      });
    }
    loadHistory(currentUrl);
  }

  const detail = document.querySelector("#inspection-detail");
  if (detail) {
    const alertBox = document.querySelector("#detail-alert");
    const renderDetail = (item) => {
      const image = item.image_url
        ? `<img class="detail-image" src="${escapeHtml(item.image_url)}" alt="Inspection image">`
        : '<div class="alert alert-secondary">No image was saved for this inspection.</div>';
      const review = item.review
        ? `<dl class="row mb-0"><dt class="col-sm-4">Reviewed class</dt><dd class="col-sm-8">${escapeHtml(item.review.reviewed_class)}</dd><dt class="col-sm-4">Reviewer</dt><dd class="col-sm-8">${escapeHtml(item.review.reviewer)}</dd><dt class="col-sm-4">Comment</dt><dd class="col-sm-8">${escapeHtml(item.review.comment || "—")}</dd><dt class="col-sm-4">Reviewed at</dt><dd class="col-sm-8">${new Date(item.review.reviewed_at).toLocaleString()}</dd></dl>`
        : '<p class="text-secondary mb-0">No review has been submitted.</p>';
      detail.innerHTML = `<div class="row g-4">
        <div class="col-lg-6">${image}</div>
        <div class="col-lg-6">
          <div class="card mb-3"><div class="card-body"><h2 class="h5">Original model output</h2><dl class="row mb-0"><dt class="col-sm-5">Status</dt><dd class="col-sm-7">${statusBadge(item.status)}</dd><dt class="col-sm-5">Product</dt><dd class="col-sm-7">${escapeHtml(item.product_name)} (${escapeHtml(item.product_id)})</dd><dt class="col-sm-5">Prediction</dt><dd class="col-sm-7">${escapeHtml(item.predicted_class || "—")}</dd><dt class="col-sm-5">Confidence</dt><dd class="col-sm-7">${formatPercent(item.confidence)}</dd><dt class="col-sm-5">Defect probability</dt><dd class="col-sm-7">${formatPercent(item.defect_probability)}</dd><dt class="col-sm-5">Model version</dt><dd class="col-sm-7">${escapeHtml(item.model_version || "—")}</dd><dt class="col-sm-5">Error</dt><dd class="col-sm-7 text-danger">${escapeHtml(item.error_message || "—")}</dd></dl></div></div>
          <div class="card"><div class="card-body"><h2 class="h5">Supervisor review</h2>${review}</div></div>
        </div>
      </div>`;
      if (item.review) {
        const choice = document.querySelector("#detail-reviewed-class");
        const comment = document.querySelector("#detail-review-comment");
        if (choice) choice.value = item.review.reviewed_class;
        if (comment) comment.value = item.review.comment;
      }
    };
    apiRequest(detail.dataset.apiUrl)
      .then(renderDetail)
      .catch((error) => {
        showAlert(alertBox, error.message);
        detail.textContent = "";
      });
    const reviewForm = document.querySelector("#detail-review-form");
    if (reviewForm) {
      reviewForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
          await apiRequest(reviewForm.dataset.reviewUrlTemplate.replace("{id}", detail.dataset.inspectionId), {
            method: "POST",
            body: JSON.stringify({
              reviewed_class: document.querySelector("#detail-reviewed-class").value,
              comment: document.querySelector("#detail-review-comment").value,
            }),
          });
          showAlert(alertBox, "Review saved.", "success");
          const item = await apiRequest(detail.dataset.apiUrl);
          renderDetail(item);
        } catch (error) {
          showAlert(alertBox, error.message);
        }
      });
    }
  }
})();
