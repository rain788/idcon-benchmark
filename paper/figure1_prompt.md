# 图 1（方法示意图）生图 prompt

用途：论文第 1 页右栏图 1，单栏宽（约 8.5 cm × 5.5 cm），文件名 `figures/fig1_task.pdf`（生成 PNG 后我可以转成 PDF 放进去；建议导出 ≥ 2400 px 宽）。

## 风格参考（我看过的同类论文图）
SIGMOD/VLDB/KDD 子图匹配论文（如 CECI、FIRST、Sun & Luo 2020 的 Figure 1）的共同做法：
- 白底、扁平矢量风格，无阴影、无渐变、无 3D、无写实元素；
- 左边小的查询图（pattern），右边较大的数据图（data graph），节点是带细描边的圆，节点内写短标签（u1…/v1…）；
- 用 2–3 种低饱和色区分不同的嵌入（embedding），嵌入用同色的高亮描边或虚线箭头表示映射；
- 细线条（约 0.75 pt），无衬线字体（Helvetica/Arial 风格），文字很少，面板用 (a)(b)(c) 标注；
- 色盲友好配色：蓝 #3B6EA8、橙 #E08A2E、灰 #8C8C8C，状态色 S=绿 #4E9A5B、U=黄 #D9B23A、V=红 #C4473E。

## 英文 prompt（直接粘贴到生图工具）

A clean, flat vector scientific diagram for a computer-science conference paper (ACM KDD style), white background, single-column figure with aspect ratio about 3:2, thin 0.75 pt dark-grey lines, sans-serif labels (Helvetica-like), no shadows, no gradients, no 3D, no clip-art, minimal text.

Three panels from left to right, labeled "(a)", "(b)", "(c)" in small bold text at the top-left of each panel.

Panel (a), titled "Requirement graph Q": a small pattern graph with 4 circular nodes labeled "r1", "r2", "r3", "r" connected in a simple tree (r1–r2, r2–r3, r2–r). The node "r" has a double outline to mark it as the checked role. Below the graph, a tiny caption "checked role: r".

Panel (b), titled "Observed graph G": a larger graph of about 12 circular nodes labeled "v1" to "v12" with sparse edges, containing two overlapping copies of the pattern. Two admissible embeddings are highlighted: embedding y1 with a blue (#3B6EA8) outline around its 4 nodes, embedding y2 with an orange (#E08A2E) outline around its 4 nodes; three nodes are shared by both embeddings, only the image of the checked role differs. Each node in the graph has a tiny square badge in its upper-right corner showing its observation: green "S" (#4E9A5B) on most nodes, one node with red "V" (#C4473E), one node with yellow "U" (#D9B23A). The image of r under y1 carries a green "S" badge; the image of r under y2 carries a red "V" badge. Thin dashed arrows from panel (a) node "r" point to these two nodes, in blue and orange respectively.

Panel (c), titled "Diagnosis": two short stacked boxes. Top box, light grey, labeled "First match" with the text "returns y1 → SATISFIES  or  y2 → VIOLATES (depends on search order)". Bottom box, outlined in dark grey, labeled "Identity consensus" with the text "{S, V} over all admissible identities → UNKNOWN", with a small check mark. Under the boxes, one line of tiny text: "empty identity space → EMPTY".

Overall: balanced whitespace, consistent stroke widths, all text horizontal and legible at small size, colour-blind-safe palette, publication quality, vector-like crisp edges.

## 负面提示（如工具支持）
photorealistic, 3D, shading, gradient, glossy, cartoon characters, handwriting font, dense text, watermark, logo, dark background, perspective view

## 中文说明（给你核对内容）
- (a) 需求图 Q：4 个角色，r 是被检查的角色；
- (b) 观测图 G：两个合法嵌入 y1（蓝）、y2（橙），只在 r 的落点上不同，一个落点观测为 S，另一个为 V；
- (c) 诊断：首次匹配（first match）的答案取决于搜索顺序；身份共识给出 UNKNOWN；没有任何合法嵌入时给出 EMPTY。
生成后请检查：节点标签拼写、S/U/V 颜色是否与图注一致、文字是否可读。
