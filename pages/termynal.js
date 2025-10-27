class Termynal {
  constructor(container, options = {}) {
    this.container = container;
    this.options = {
      typeDelay: 50,
      lineDelay: 900,
      startDelay: this._parseDelay(container.dataset.tyStartDelay) || 0,
      loop: options.loop ?? container.dataset.termynalLoop !== undefined,
      ...options,
    };
    this.lines = Array.from(container.querySelectorAll("[data-ty]")).map(
      (node) => ({
        type: node.dataset.ty === "input" ? "input" : "text",
        content: this._decode(node.innerHTML),
        delay: this._parseDelay(node.dataset.tyDelay),
      })
    );
    this._timeouts = [];
    this._createStage();
  }

  _parseDelay(value) {
    if (!value) {
      return undefined;
    }
    const parsed = Number.parseInt(value, 10);
    return Number.isNaN(parsed) ? undefined : parsed;
  }

  _decode(value) {
    const doc = document.implementation.createHTMLDocument("");
    doc.body.innerHTML = value;
    return doc.body.textContent || "";
  }

  _createStage() {
    this.container.innerHTML = "";
    this.currentLine = 0;
    this._timeouts.forEach(clearTimeout);
    this._timeouts = [];
    const startTimer = setTimeout(
      () => this._showNextLine(),
      this.options.startDelay
    );
    this._timeouts.push(startTimer);
  }

  _showNextLine() {
    if (this.currentLine >= this.lines.length) {
      if (this.options.loop) {
        const resetTimer = setTimeout(() => this._createStage(), 1500);
        this._timeouts.push(resetTimer);
      }
      return;
    }

    const line = this.lines[this.currentLine];
    const lineElement = document.createElement("div");
    lineElement.className = "termynal-line";
    if (line.type === "input") {
      lineElement.classList.add("termynal-line--input");
    }

    const textNode = document.createTextNode("");
    const cursor = document.createElement("span");
    cursor.className = "termynal__cursor";
    cursor.innerHTML = "&#9612;";

    lineElement.appendChild(textNode);
    lineElement.appendChild(cursor);
    this.container.appendChild(lineElement);

    requestAnimationFrame(() =>
      lineElement.classList.add("termynal-line--shown")
    );

    this._typeLine(line, textNode, cursor);
    this.currentLine += 1;
  }

  _typeLine(line, textNode, cursor) {
    let position = 0;
    const { content } = line;
    const typeDelay = Math.max(this.options.typeDelay, 10);

    const typeNext = () => {
      if (position < content.length) {
        textNode.textContent += content[position];
        position += 1;
        const timer = setTimeout(typeNext, typeDelay);
        this._timeouts.push(timer);
      } else {
        cursor.remove();
        const delay = line.delay ?? this.options.lineDelay;
        const timer = setTimeout(() => this._showNextLine(), delay);
        this._timeouts.push(timer);
      }
    };

    typeNext();
  }
}
