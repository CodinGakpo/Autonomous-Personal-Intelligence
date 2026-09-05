// Direct port of brain/mail_tree.html's D3 collapsible-tree rendering into React. The D3 code
// itself is unchanged (same layout math, same interactions) — only the fetch/mount wiring is
// React-flavored, since the original was a small imperative script with no state.
import * as d3 from "d3"
import { useEffect, useRef, useState } from "react"

import { type MailNode, reclassifyThread } from "@/lib/brainApi"

import "./MailMindmap.css"

type HierarchyNode = d3.HierarchyNode<MailNode> & {
  x0?: number
  y0?: number
  _children?: HierarchyNode[] | null
}

const COLORS: Record<string, string> = {
  root: "#6b7a99",
  mail_category: "#6b7a99",
  mail_topic: "#3fae90",
  mail_thread: "#5b8cff",
}

const DURATION = 260
const NODE_HEIGHT = 44
const NODE_GAP_Y = 14
const LEVEL_WIDTH = 260

function textWidth(text: string): number {
  return Math.max(150, Math.min(320, 16 + text.length * 7.2))
}

function collapse(d: HierarchyNode) {
  if (d.children) {
    d._children = d.children as HierarchyNode[]
    d._children.forEach(collapse)
    d.children = undefined
  }
}

function toggleNode(d: HierarchyNode) {
  if (d.children) {
    d._children = d.children as HierarchyNode[]
    d.children = undefined
  } else if (d._children) {
    d.children = d._children
    d._children = null
  }
}

interface NodeCounts {
  mail_category: number
  mail_topic: number
  mail_thread: number
}

function countNodes(n: MailNode): NodeCounts {
  const counts: NodeCounts = { mail_category: 0, mail_topic: 0, mail_thread: 0 }
  const walk = (node: MailNode) => {
    if (node.type in counts) counts[node.type as keyof NodeCounts]++
    ;(node.children || []).forEach(walk)
  }
  walk(n)
  return counts
}

export function MailMindmap({
  data,
  onReclassified,
  onAskAbout,
}: {
  data: MailNode
  onReclassified?: () => void | Promise<void>
  /** Open a chat seeded with a question about the selected thread. */
  onAskAbout?: (question: string) => void
}) {
  const chartRef = useRef<HTMLDivElement>(null)
  const [detail, setDetail] = useState<HierarchyNode | null>(null)
  const [counts, setCounts] = useState({ mail_category: 0, mail_topic: 0, mail_thread: 0 })
  const [moveTo, setMoveTo] = useState("")
  const [moving, setMoving] = useState(false)
  const [moveError, setMoveError] = useState<string | null>(null)

  const categoryNames = (data.children || []).map((c) => c.name)
  // ancestors() is [thread, topic, category, root]; the category is the third entry.
  const currentCategory = detail?.ancestors().reverse().slice(1, -1)[0]?.data.name ?? ""

  // Default the picker to wherever the thread currently sits each time one is opened.
  useEffect(() => {
    setMoveTo(currentCategory)
    setMoveError(null)
  }, [currentCategory])

  async function handleMove() {
    if (!detail || !moveTo || moveTo === currentCategory) return
    setMoving(true)
    setMoveError(null)
    try {
      await reclassifyThread(detail.data.id, moveTo)
      // The tree is rebuilt from scratch on new `data`, and this node belongs to the old one —
      // close the panel rather than leave it rendering a stale node.
      setDetail(null)
      await onReclassified?.()
    } catch (err) {
      setMoveError(err instanceof Error ? err.message : "Couldn't move this thread.")
    } finally {
      setMoving(false)
    }
  }

  useEffect(() => {
    setCounts(countNodes(data))
    if (!chartRef.current) return
    chartRef.current.innerHTML = ""

    const svg = d3
      .select(chartRef.current)
      .append("svg")
      .style("width", "100%")
      .style("height", "100%")
    const zoomLayer = svg.append("g")
    const linkLayer = zoomLayer.append("g").attr("class", "links")
    const nodeLayer = zoomLayer.append("g").attr("class", "nodes")

    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.3, 2])
      .on("zoom", (ev) => zoomLayer.attr("transform", ev.transform.toString()))
    svg.call(zoom)
    svg.on("mousedown.grab", () => chartRef.current?.classList.add("grabbing"))
    svg.on("mouseup.grab", () => chartRef.current?.classList.remove("grabbing"))

    const nodeDepthColor = (d: HierarchyNode) => COLORS[d.data.type] || "#6b7a99"

    function update(source: HierarchyNode, root: HierarchyNode) {
      const treeData = d3
        .tree<MailNode>()
        .nodeSize([NODE_HEIGHT + NODE_GAP_Y, LEVEL_WIDTH])(root as d3.HierarchyNode<MailNode>)
      const nodes = treeData.descendants() as HierarchyNode[]
      const links = treeData.links()

      nodes.forEach((d) => {
        d.y = d.depth * LEVEL_WIDTH
      })

      const node = nodeLayer.selectAll<SVGGElement, HierarchyNode>("g.node").data(nodes, (d) => d.data.id)

      const nodeEnter = node
        .enter()
        .append("g")
        .attr("class", (d) => "node " + d.data.type)
        .attr("transform", () => `translate(${source.y0 ?? 0},${source.x0 ?? 0})`)
        .style("opacity", 0)
        .on("click", (_ev, d) => {
          if (d.data.type === "mail_thread") {
            setDetail(d)
            return
          }
          toggleNode(d)
          update(d, root)
        })

      nodeEnter
        .append("rect")
        .attr("width", (d) => textWidth(d.data.name))
        .attr("height", NODE_HEIGHT)
        .attr("x", 0)
        .attr("y", -NODE_HEIGHT / 2)
        .attr("stroke", nodeDepthColor)

      nodeEnter
        .append("text")
        .attr("x", 16)
        .attr("y", 2)
        .attr("dominant-baseline", "central")
        .text((d) => (d.data.name.length > 40 ? d.data.name.slice(0, 38) + "…" : d.data.name))

      // Amber dot on threads the classifier wasn't sure about, so a wrong filing is visible
      // at a glance rather than only discoverable by opening every thread.
      nodeEnter
        .filter((d) => Boolean(d.data.needs_review))
        .append("circle")
        .attr("class", "review-flag")
        .attr("r", 4)
        .attr("cx", 8)
        .attr("cy", -NODE_HEIGHT / 2 + 8)

      const toggleGroup = nodeEnter
        .filter((d) => d.data.type !== "mail_thread")
        .append("g")
        .attr("class", "toggle")
      toggleGroup.attr("transform", (d) => `translate(${textWidth(d.data.name) + 14},0)`)
      toggleGroup.append("circle").attr("r", 10)
      toggleGroup.append("text").text((d) => (d.children ? "<" : d._children || d.data.children ? ">" : ""))

      const nodeUpdate = nodeEnter.merge(node)
      nodeUpdate
        .transition()
        .duration(DURATION)
        .attr("transform", (d) => `translate(${d.y},${d.x})`)
        .style("opacity", 1)
      nodeUpdate
        .select(".toggle text")
        .text((d) =>
          d.children ? "<" : d._children || (d.data.children && d.data.children.length) ? ">" : "",
        )

      node
        .exit()
        .transition()
        .duration(DURATION)
        .attr("transform", () => `translate(${source.y},${source.x})`)
        .style("opacity", 0)
        .remove()

      const link = linkLayer.selectAll<SVGPathElement, d3.HierarchyLink<MailNode>>("path.link").data(
        links,
        (d) => (d.target as HierarchyNode).data.id,
      )

      const diagonal = (s: HierarchyNode, t: HierarchyNode) => {
        const sx = (s.y ?? 0) + textWidth(s.data.name)
        const sy = s.x ?? 0
        const tx = t.y ?? 0
        const ty = t.x ?? 0
        const mx = (sx + tx) / 2
        return `M${sx},${sy} C${mx},${sy} ${mx},${ty} ${tx},${ty}`
      }

      const linkEnter = link
        .enter()
        .insert("path", "g")
        .attr("class", "link")
        .attr("d", () => {
          const o = { x: source.x0 ?? 0, y: source.y0 ?? 0, data: { name: "" } } as HierarchyNode
          return diagonal(o, o)
        })

      linkEnter
        .merge(link)
        .transition()
        .duration(DURATION)
        .attr("d", (d) => diagonal(d.source as HierarchyNode, d.target as HierarchyNode))

      link
        .exit()
        .transition()
        .duration(DURATION)
        .attr("d", () => {
          const o = { x: source.x, y: source.y, data: { name: "" } } as HierarchyNode
          return diagonal(o, o)
        })
        .remove()

      nodes.forEach((d) => {
        d.x0 = d.x
        d.y0 = d.y
      })
    }

    const root = d3.hierarchy(data) as HierarchyNode
    root.x0 = 0
    root.y0 = 0
    // Start with categories expanded, topics collapsed — matches brain/mail_tree.html.
    root.children?.forEach((cat) => {
      ;((cat as HierarchyNode).children || []).forEach((topic) => collapse(topic as HierarchyNode))
    })
    update(root, root)

    const svgNode = svg.node()
    if (svgNode) {
      const initialScale = 0.9
      svg.call(
        zoom.transform,
        d3.zoomIdentity.translate(60, svgNode.clientHeight / 2).scale(initialScale),
      )
    }

  }, [data])

  return (
    <div className="mail-mindmap-root">
      <div className="mail-mindmap-chart" ref={chartRef} />
      <div className="mail-mindmap-hint">scroll to zoom · drag to pan</div>
      <div className="mail-mindmap-counts" style={{ position: "absolute", top: 12, left: 16, fontSize: 12, color: "var(--mm-muted)" }}>
        <b style={{ color: "var(--mm-ink)" }}>{counts.mail_category}</b> categories ·{" "}
        <b style={{ color: "var(--mm-ink)" }}>{counts.mail_topic}</b> topics ·{" "}
        <b style={{ color: "var(--mm-ink)" }}>{counts.mail_thread}</b> threads
      </div>

      <div className={`mail-mindmap-detail${detail ? " open" : ""}`}>
        {detail && (
          <>
            <button className="close" onClick={() => setDetail(null)}>
              &times;
            </button>
            {onAskAbout && (
              <button
                className="ask-btn"
                onClick={() => onAskAbout(`Tell me about "${detail.data.name}".`)}
              >
                Ask about this
              </button>
            )}
            <div className="path">
              {detail
                .ancestors()
                .reverse()
                .slice(1, -1)
                .map((n) => n.data.name)
                .join(" › ")}
            </div>
            <h2>{detail.data.name}</h2>

            <div className="lbl">Category</div>
            {detail.data.needs_review && (
              <div className="review-note">
                Low confidence — check this category.
                {detail.data.classification?.llm_category &&
                detail.data.classification.llm_category !==
                  detail.data.classification.keyword_category ? (
                  <>
                    {" "}
                    The keyword rules said{" "}
                    <b>{detail.data.classification.keyword_category}</b>, the model said{" "}
                    <b>{detail.data.classification.llm_category}</b>.
                  </>
                ) : null}
              </div>
            )}
            <div className="move-row">
              {/* A datalist-backed input, not a <select>: the right category often doesn't
                  exist yet (that's how a thread got misfiled), and the API creates one on
                  demand. This lets the user pick an existing category or type a new one,
                  without pulling in a combobox dependency. */}
              <input
                list="mail-mindmap-categories"
                value={moveTo}
                onChange={(e) => setMoveTo(e.target.value)}
                aria-label="Move to category"
                placeholder="Category…"
              />
              <datalist id="mail-mindmap-categories">
                {categoryNames.map((name) => (
                  <option key={name} value={name} />
                ))}
              </datalist>
              <button
                className="move-btn"
                disabled={moving || !moveTo || moveTo === currentCategory}
                onClick={handleMove}
              >
                {moving ? "Moving…" : "Move"}
              </button>
            </div>
            {moveError && <div className="move-error">{moveError}</div>}

            <div className="lbl">Summary</div>
            <div className="summary">{detail.data.summary || "(no summary)"}</div>
            {detail.data.body && (
              <>
                <div className="lbl">Full content</div>
                <div className="body">{detail.data.body}</div>
              </>
            )}
            {detail.data.source_uids && detail.data.source_uids.length > 0 && (
              <>
                <div className="lbl">Source emails</div>
                <div className="uids">
                  {detail.data.source_uids.map((u) => (
                    <span className="uid" key={u}>
                      uid {u}
                    </span>
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}
