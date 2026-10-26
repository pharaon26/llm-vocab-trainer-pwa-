const SVG_NS = "http://www.w3.org/2000/svg";

function build(node, props, children) {
  for (const [key, value] of Object.entries(props)) {
    if (value == null || value === false) {
      continue;
    }
    if (key.startsWith("on")) {
      node.addEventListener(key.slice(2), value);
    } else if (key === "className") {
      node.setAttribute("class", value);
    } else {
      node.setAttribute(key, value === true ? "" : value);
    }
  }
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false) {
      continue;
    }
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function el(tag, props = {}, ...children) {
  return build(document.createElement(tag), props, children);
}

export function svg(tag, props = {}, ...children) {
  return build(document.createElementNS(SVG_NS, tag), props, children);
}

export function clear(node) {
  node.replaceChildren();
}
