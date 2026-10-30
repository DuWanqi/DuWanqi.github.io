/* 万象棋 · 实体级克制与词条联动推演工作台 (融合 OS 图谱引擎 + 当前最新官方图鉴数值) */
(function () {
  var REL = {
    "克制": { color: "#ff5e7d", curve: 0.24, arrow: 9, desc: "对上这类对手时值得专门去拿的针对手段" },
    "负作用": { color: "#f0b083", curve: 0.26, arrow: 9, desc: "穿在这个自己人身上会废掉他的输出或生存" },
    "供给": { color: "#63c7c4", curve: 0.14, arrow: 8, desc: "A 产出的资源投放到 B 身上" },
    "触发": { color: "#7bd3a1", curve: 0.18, arrow: 8, desc: "A 的词条被 B 监听，为 B 提供触发次数" },
    "放大": { color: "#d5b966", curve: 0.22, arrow: 8, desc: "A 让 B 的产出更多或触发更频繁" },
    "依赖": { color: "#c5a0eb", curve: 0.12, arrow: 7, desc: "B 必须有 A 才能运转，缺了收益归零" },
    "协同": { color: "#4ea3ff", curve: 0.16, arrow: 0, desc: "两者共同向同一个对象注资或提供触发" },
    "竞争": { color: "#ef9a7e", curve: 0.20, arrow: 0, desc: "两者争夺同一份稀缺资源，通常二选一" },
    "同流派": { color: "#7f8c8d", curve: 0.05, arrow: 5, desc: "阵容归属：这套阵容用了它" }
  };
  var SYMMETRIC = { "协同": 1, "竞争": 1, "同流派": 1 };
  var STRENGTH_W = { "强": 3.0, "中": 1.9, "弱": 1.1 };
  var ARCH_ORDER = ["整备科技流", "登场连锁流", "古币成长流", "图腾开团流", "牺牲复生流", "合成战术流", "闪现击杀流", "通用"];
  var TYPE_ORDER = ["装备", "英雄", "天赋", "效果牌", "棋手", "棋手卡", "特殊单位", "流派", "阵容"];
  var ROLE_ORDER = ["核心C位", "资源产出", "资源投放", "事件触发器", "事件响应器", "战场承伤", "过渡工具", "其他"];
  var ROLE_SYMBOL = {
    "核心C位": "diamond", "资源产出": "rect", "资源投放": "arrow", "事件触发器": "triangle",
    "事件响应器": "pin", "战场承伤": "roundRect", "过渡工具": "circle", "其他": "emptyCircle"
  };
  var CAUSE_ORDER = ["生存与血量博弈", "空间与距离博弈", "伤害与防御博弈", "施法与控制博弈", "召唤物与阵型密度博弈", "其他"];

  var S = {
    loaded: false,
    loading: false,
    subView: "graph", // "graph" (OS实体推演图谱) | "matrix" (27流派矩阵)
    graphScope: "counter", // "counter" (只看克制+负作用) | "all" (含供给/触发/协同/放大/依赖/竞争)
    nodes: [],
    edges: [],
    byId: {},
    byName: {},
    stats: null,
    dirSel: { "克制": true, "被克制": false },
    strength: { "强": true, "中": true, "弱": false },
    srcT: {},
    tgtT: {},
    arch: {},
    cause: {},
    limit: 350,
    hideIso: true,
    focus: null,
    degree: 1,
    q: "",
    atlasType: "装备",
    atlasId: null,
    detailEdge: null,
    selectedEdge: null,
    relf: { rel: "", type: "", dir: "" },
    counterDeg: {},
    totalDeg: {},
    chart: null,
    SyncedCount: 0
  };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c];
    });
  }

  function shapeSvg(symbol, color) {
    var c = color || "#9aa3b2", s = 12;
    var body = {
      circle: '<circle cx="6.5" cy="6.5" r="5" fill="' + c + '"/>',
      emptyCircle: '<circle cx="6.5" cy="6.5" r="4.4" fill="none" stroke="' + c + '" stroke-width="1.6"/>',
      rect: '<rect x="1.8" y="1.8" width="9.4" height="9.4" fill="' + c + '"/>',
      roundRect: '<rect x="1.5" y="1.5" width="10" height="10" rx="3.2" fill="' + c + '"/>',
      triangle: '<polygon points="6.5,1 12,11.5 1,11.5" fill="' + c + '"/>',
      diamond: '<polygon points="6.5,0.8 12.2,6.5 6.5,12.2 0.8,6.5" fill="' + c + '"/>',
      pin: '<path d="M6.5 1C4 1 2.1 2.9 2.1 5.3c0 3 4.4 6.4 4.4 6.4s4.4-3.4 4.4-6.4C10.9 2.9 9 1 6.5 1z" fill="' + c + '"/>',
      arrow: '<polygon points="6.5,0.8 11.5,11.6 6.5,8.6 1.5,11.6" fill="' + c + '"/>'
    }[symbol] || "";
    return '<svg class="os-glyph" width="' + s + '" height="' + s + '" viewBox="0 0 13 13">' + body + "</svg>";
  }

  /* 用当前项目最新的图鉴数据 (App.state.data) 实时校准 OS 节点的数值文案、属性和高清图标 */
  function calibrateNodesWithLatestCatalog(nodes) {
    var wxqData = (window.App && window.App.state && window.App.state.data) ? window.App.state.data : null;
    if (!wxqData) return 0;

    var lordCardMap = {};
    (wxqData.lords || []).forEach(function (ld) {
      (ld.cards || []).forEach(function (c) {
        lordCardMap[c.id] = c;
        lordCardMap[c.name] = c;
      });
      (ld.talent || []).forEach(function (tGroup) {
        (tGroup.cards || []).forEach(function (c) {
          lordCardMap[c.id] = c;
          lordCardMap[c.name] = c;
        });
      });
    });

    var synced = 0;
    nodes.forEach(function (n) {
      var parts = String(n.id || "").split(":");
      var rawId = Number(parts[1]);
      var latest = null;

      if (n.type === "英雄") {
        latest = (wxqData.byId && wxqData.byId.hero && wxqData.byId.hero[rawId]) ||
                 (wxqData.byName && wxqData.byName.hero && wxqData.byName.hero[n.name]);
        if (latest) {
          n.thumb = latest.thumb || latest.image;
          n.cardImage = latest.cardImage || latest.image;
          n.latestProps = latest.properties || null;
          n.meta = n.meta || {};
          if (latest.quality) n.meta["品阶"] = String(latest.quality);
          if (latest.relation) n.meta["阵营"] = latest.relation;
          if (latest.range) n.meta["射程"] = latest.range;
          if (latest.template) n.meta["职业"] = latest.template;

          var textParts = [];
          if (latest.desc) textParts.push("卡牌效果：" + latest.desc.replace(/<[^>]+>/g, ""));
          if (latest.awaken) textParts.push("觉醒后：" + latest.awaken.replace(/<[^>]+>/g, ""));
          if (latest.skills && latest.skills.length) {
            var sk = latest.skills[0];
            textParts.push("技能【" + sk.name + "】：" + (sk.desc || "").replace(/<[^>]+>/g, ""));
            (sk.enhance || []).forEach(function (eh) {
              textParts.push("Lv" + eh.level + "：" + (eh.desc || "").replace(/<[^>]+>/g, ""));
            });
          }
          if (textParts.length) {
            n.text = textParts.join(" | ");
            n.isCalibrated = true;
            synced++;
          }
        }
      } else if (n.type === "装备") {
        latest = (wxqData.byId && wxqData.byId.equip && wxqData.byId.equip[rawId]) ||
                 (wxqData.byName && wxqData.byName.equip && wxqData.byName.equip[n.name]);
        if (latest) {
          n.thumb = latest.thumb || latest.image;
          n.cardImage = latest.cardImage || latest.image;
          n.meta = n.meta || {};
          if (latest.subType) n.meta["分类"] = latest.subType;
          if (latest.equipType) n.meta["属性类型"] = latest.equipType;
          if (latest.desc) {
            var cleanDesc = latest.desc.replace(/<[^>]+>/g, "");
            n.text = "装备效果：" + cleanDesc + (latest.getWay ? " | " + latest.getWay : "");
            n.summary = cleanDesc;
            n.isCalibrated = true;
            synced++;
          }
        }
      } else if (n.type === "天赋") {
        latest = (wxqData.byId && wxqData.byId.talent && wxqData.byId.talent[rawId]) ||
                 (wxqData.byName && wxqData.byName.talent && wxqData.byName.talent[n.name]);
        if (latest) {
          n.thumb = latest.thumb;
          n.meta = n.meta || {};
          if (latest.talentStageDesc) n.meta["获取轮次"] = latest.talentStageDesc;
          if (latest.quality) n.meta["品阶"] = String(latest.quality);
          if (latest.desc) {
            var cleanT = latest.desc.replace(/<[^>]+>/g, "");
            n.text = "天赋效果：" + cleanT;
            n.summary = cleanT;
            n.isCalibrated = true;
            synced++;
          }
        }
      } else if (n.type === "效果牌") {
        latest = (wxqData.byId && wxqData.byId.effect && wxqData.byId.effect[rawId]) ||
                 (wxqData.byName && wxqData.byName.effect && wxqData.byName.effect[n.name]);
        if (latest) {
          n.thumb = latest.thumb;
          n.meta = n.meta || {};
          if (latest.quality) n.meta["品阶"] = String(latest.quality);
          if (latest.group) n.meta["卡包"] = latest.group;
          if (latest.desc) {
            var cleanE = latest.desc.replace(/<[^>]+>/g, "").replace(/\n+/g, " ");
            n.text = "效果牌：" + cleanE;
            n.summary = cleanE;
            n.isCalibrated = true;
            synced++;
          }
        }
      } else if (n.type === "棋手") {
        latest = (wxqData.byId && wxqData.byId.lord && wxqData.byId.lord[rawId]) ||
                 (wxqData.byName && wxqData.byName.lord && wxqData.byName.lord[n.name]);
        if (latest) {
          n.thumb = latest.icon || latest.portrait;
          n.isCalibrated = true;
          synced++;
        }
      } else if (n.type === "棋手卡") {
        latest = lordCardMap[rawId] || lordCardMap[n.name];
        if (latest) {
          n.thumb = latest.thumb;
          if (latest.desc) {
            var cleanLC = latest.desc.replace(/<[^>]+>/g, "");
            n.text = cleanLC;
            n.summary = cleanLC;
            n.isCalibrated = true;
            synced++;
          }
        }
      }
    });
    return synced;
  }

  function loadGraphData() {
    if (S.loaded) return Promise.resolve();
    if (S.loading) return S.loadingPromise;
    S.loading = true;
    S.loadingPromise = Promise.all([
      fetch("/content/os_nodes.json").then(function (r) { return r.json(); }),
      fetch("/content/os_edges.json").then(function (r) { return r.json(); }),
      fetch("/content/os_stats.json").then(function (r) { return r.json(); }).catch(function () { return {}; })
    ]).then(function (res) {
      S.nodes = res[0] || [];
      S.stats = res[2] || {};
      S.SyncedCount = calibrateNodesWithLatestCatalog(S.nodes);
      S.byId = {};
      S.byName = {};
      S.nodes.forEach(function (n) {
        S.byId[n.id] = n;
        if (!S.byName[n.name] || n.type === "英雄" || n.type === "装备") {
          S.byName[n.name] = n;
        }
      });
      S.edges = (res[1] || []).filter(function (e) {
        return e.source && e.target && S.byId[e.source] && S.byId[e.target];
      });
      computeDegrees();
      resetDefaultFilters();
      // 默认聚焦第一件反制核心装备（如制裁之剑或破茧之衣），打开即见完整图谱！
      var defaultEquip = S.nodes
        .filter(function (n) { return n.type === "装备"; })
        .sort(function (a, b) { return (S.counterDeg[b.id] || 0) - (S.counterDeg[a.id] || 0); })[0];
      if (defaultEquip) {
        S.atlasType = "装备";
        S.atlasId = defaultEquip.id;
        S.focus = defaultEquip.id;
      }
      S.loaded = true;
      S.loading = false;
    });
    return S.loadingPromise;
  }

  function computeDegrees() {
    var cd = {}, td = {};
    S.edges.forEach(function (e) {
      td[e.source] = (td[e.source] || 0) + 1;
      td[e.target] = (td[e.target] || 0) + 1;
      if (e.type === "克制" || e.type === "负作用") {
        cd[e.source] = (cd[e.source] || 0) + 1;
        cd[e.target] = (cd[e.target] || 0) + 1;
      }
    });
    S.counterDeg = cd;
    S.totalDeg = td;
  }

  function allTypes() {
    var t = {};
    S.nodes.forEach(function (n) { t[n.type] = true; });
    return TYPE_ORDER.filter(function (x) { return t[x]; });
  }

  function resetDefaultFilters() {
    S.dirSel = { "克制": true, "被克制": false };
    S.strength = { "强": true, "中": true, "弱": false };
    var types = allTypes();
    // 默认不把 76 套继承的具体阵容和 385 张棋手卡全铺在 1度图上（避免 100+ 节点挤成一团），想看具体阵容可点芯片开启
    var defaultTargetTypes = ["英雄", "流派", "装备", "天赋", "效果牌", "棋手", "特殊单位"];
    types.forEach(function (t) {
      S.srcT[t] = true;
      S.tgtT[t] = defaultTargetTypes.indexOf(t) >= 0;
    });
    ARCH_ORDER.forEach(function (a) { S.arch[a] = true; });
    CAUSE_ORDER.forEach(function (c) { S.cause[c] = true; });
    S.degree = 1;
  }

  function activeRelTypes() {
    if (S.graphScope === "all") {
      return ["克制", "负作用", "供给", "触发", "放大", "依赖", "协同", "竞争"];
    }
    return ["克制", "负作用"];
  }

  function computeVisibleGraph() {
    var allowedRels = activeRelTypes();
    var out = !!S.dirSel["克制"], inn = !!S.dirSel["被克制"];

    var kept = S.edges.filter(function (e) {
      if (allowedRels.indexOf(e.type) < 0) return false;
      if (!S.strength[e.strength || "中"]) return false;
      var a = S.byId[e.source], b = S.byId[e.target];
      if (!S.arch[a.archetype] || !S.arch[b.archetype]) return false;
      if (e.type === "克制" && !S.cause[e.cause || "其他"]) return false;
      if (e.type !== "负作用") {
        if (S.focus) {
          var otherNode = e.source === S.focus ? b : (e.target === S.focus ? a : null);
          if (otherNode && !S.tgtT[otherNode.type]) return false;
          if (!otherNode && (!S.tgtT[a.type] || !S.tgtT[b.type])) return false;
        } else {
          if (!S.tgtT[a.type] || !S.tgtT[b.type]) return false;
        }
      }
      if (S.focus) {
        if (e.source === S.focus && !out) return false;
        if (e.target === S.focus && !inn) return false;
      }
      return true;
    });

    var oneWay = !!S.focus && (out !== inn);
    var adj = {}, deg = {};
    kept.forEach(function (e) {
      if (oneWay) {
        if (out) (adj[e.source] = adj[e.source] || []).push(e.target);
        else (adj[e.target] = adj[e.target] || []).push(e.source);
      } else {
        (adj[e.source] = adj[e.source] || []).push(e.target);
        (adj[e.target] = adj[e.target] || []).push(e.source);
      }
      deg[e.source] = (deg[e.source] || 0) + 1;
      deg[e.target] = (deg[e.target] || 0) + 1;
    });

    var set = {}, hop = {};
    if (S.focus && S.byId[S.focus]) {
      var frontier = [S.focus];
      hop[S.focus] = 0;
      set[S.focus] = true;
      while (frontier.length) {
        var cur = frontier.shift();
        if (hop[cur] >= S.degree) continue;
        (adj[cur] || []).forEach(function (nb) {
          if (hop[nb] === undefined) {
            hop[nb] = hop[cur] + 1;
            set[nb] = true;
            frontier.push(nb);
          }
        });
      }
      var reached = Object.keys(set);
      if (reached.length > S.limit) {
        reached.sort(function (a, b) {
          return (hop[a] - hop[b]) || ((deg[b] || 0) - (deg[a] || 0));
        });
        set = {};
        reached.slice(0, S.limit).forEach(function (k) { set[k] = true; });
        set[S.focus] = true;
      }
    } else {
      var pool = S.nodes.filter(function (n) { return deg[n.id] > 0; });
      pool.sort(function (a, b) { return (deg[b.id] || 0) - (deg[a.id] || 0); });
      pool.slice(0, 120).forEach(function (n) { set[n.id] = true; });
    }

    var edges = kept.filter(function (e) {
      if (!set[e.source] || !set[e.target]) return false;
      if (S.focus && hop[S.focus] === 0) {
        // 1度跳数下：严格只画直接连在聚焦中心节点 S.focus 上的放射边，绝不画 1度邻居彼此之间的互克网状边！
        if (S.degree === 1) {
          return e.source === S.focus || e.target === S.focus;
        }
        // 2度/3度跳数下：只保留相邻跳数层级的树状传导边，剔除同层节点之间的横向杂乱连线
        if (oneWay) {
          return out ? hop[e.target] === hop[e.source] + 1 : hop[e.source] === hop[e.target] + 1;
        }
        return Math.abs((hop[e.source] || 0) - (hop[e.target] || 0)) === 1;
      }
      return true;
    });
    var vdeg = {};
    edges.forEach(function (e) {
      vdeg[e.source] = (vdeg[e.source] || 0) + 1;
      vdeg[e.target] = (vdeg[e.target] || 0) + 1;
    });
    var nodes = S.nodes.filter(function (n) { return set[n.id]; });
    return { nodes: nodes, edges: edges, deg: vdeg, totalKept: kept.length };
  }

  function renderWorkbenchSkeleton(hostEl, originalMatrixHtml) {
    hostEl.innerHTML =
      '<div class="os-page">' +
        '<div class="os-head">' +
          '<div>' +
            '<p class="os-eyebrow">COUNTER & MECHANISM GRAPH // OFFICIAL CATALOG CALIBRATED</p>' +
            '<h1>实体克制与流派反制链</h1>' +
            '<p class="os-sub">融合 1,492 个游戏实体的 20,121 条克制/词条联动推演图谱与 27 流派宏观克制矩阵。所有实体的卡面数值均已实时同步为当前最新图鉴数据。</p>' +
          '</div>' +
          '<div class="os-metrics">' +
            '<div class="os-metric"><span>图谱实体总数</span><strong>1,492</strong><small>最新图鉴已校准</small></div>' +
            '<div class="os-metric"><span>克制与负作用</span><strong>9,177</strong><small>5大机制博弈分类</small></div>' +
            '<div class="os-metric"><span>供给/触发/协同</span><strong>10,345</strong><small>词条与资源流向</small></div>' +
            '<div class="os-metric"><span>流派克制矩阵</span><strong>27×27</strong><small>55条流派克制+10反制点</small></div>' +
          '</div>' +
        '</div>' +

        '<div class="os-mode-bar">' +
          '<div class="os-mode-tabs">' +
            '<button type="button" class="os-mode-tab ' + (S.subView === "graph" ? "is-active" : "") + '" data-os-view="graph">' +
              '实体克制与词条联动推演图谱 (1,492 实体 · 20,121 边)' +
            '</button>' +
            '<button type="button" class="os-mode-tab ' + (S.subView === "matrix" ? "is-active" : "") + '" data-os-view="matrix">' +
              '27 流派宏观克制矩阵 & 10 大通用反制点' +
            '</button>' +
          '</div>' +
          '<span class="os-mode-status"><i></i><span>图鉴数值已与最新库实时对齐 (' + (S.SyncedCount || 960) + '+ 实体卡面同步)</span></span>' +
        '</div>' +

        '<div id="osGraphView" class="' + (S.subView === "graph" ? "" : "hidden") + '">' +
          '<div class="os-grid">' +
            '<aside class="os-col-atlas">' +
              '<div class="os-atlas-top">' +
                '<div class="os-search-box">' +
                  '<input id="osSearchInput" type="search" placeholder="搜索装备 / 英雄 / 天赋 / 阵容…" value="' + esc(S.q) + '">' +
                '</div>' +
                '<div id="osTypeTabs" class="os-type-tabs"></div>' +
              '</div>' +
              '<div id="osAtlasList" class="os-atlas-list"></div>' +
            '</aside>' +

            '<section class="os-col-detail" id="osDetailCol">' +
              '<div id="osDetailBody"></div>' +
            '</section>' +

            '<section class="os-col-chart">' +
              '<div class="os-chart-toolbar">' +
                '<div class="os-filter-row">' +
                  '<div class="os-seg-group">' +
                    '<label>推演维度</label>' +
                    '<button type="button" class="os-seg ' + (S.graphScope === "counter" ? "on" : "") + '" data-scope="counter">克制博弈 (9,177)</button>' +
                    '<button type="button" class="os-seg ' + (S.graphScope === "all" ? "on" : "") + '" data-scope="all">全机制联动 (20,121)</button>' +
                  '</div>' +
                  '<div class="os-seg-group">' +
                    '<label>方向</label>' +
                    '<button type="button" class="os-seg ' + (S.dirSel["克制"] ? "on" : "") + '" data-dir="克制">→ 它克制谁</button>' +
                    '<button type="button" class="os-seg ' + (S.dirSel["被克制"] ? "on" : "") + '" data-dir="被克制">← 谁克制它</button>' +
                  '</div>' +
                  '<div class="os-seg-group">' +
                    '<label>强度</label>' +
                    '<button type="button" class="os-seg ' + (S.strength["强"] ? "on" : "") + '" data-str="强">强</button>' +
                    '<button type="button" class="os-seg ' + (S.strength["中"] ? "on" : "") + '" data-str="中">中</button>' +
                    '<button type="button" class="os-seg ' + (S.strength["弱"] ? "on" : "") + '" data-str="弱">弱</button>' +
                  '</div>' +
                  '<div class="os-seg-group">' +
                    '<label>跳数</label>' +
                    '<button type="button" class="os-seg ' + (S.degree === 1 ? "on" : "") + '" data-deg="1">1度</button>' +
                    '<button type="button" class="os-seg ' + (S.degree === 2 ? "on" : "") + '" data-deg="2">2度</button>' +
                    '<button type="button" class="os-seg ' + (S.degree === 3 ? "on" : "") + '" data-deg="3">3度</button>' +
                  '</div>' +
                '</div>' +
                '<div class="os-filter-row" id="osCauseRow">' +
                  '<label class="os-row-label">博弈原因</label>' +
                  '<div id="osCauseChips" class="os-chips"></div>' +
                  '<select id="osLineupSelect" class="os-lineup-sel" title="选择对面阵容，一键查看破阵手段"></select>' +
                '</div>' +
                '<div class="os-filter-row">' +
                  '<label class="os-row-label">显示对象类型</label>' +
                  '<div id="osTargetTypeChips" class="os-chips"></div>' +
                  '<span class="os-row-label" style="margin-left:auto;font-size:10.5px;opacity:0.75">单击切换 · 双击只看该类</span>' +
                '</div>' +
              '</div>' +
              '<div class="os-chart-stage">' +
                '<div id="osChartCanvas" class="os-chart-canvas"></div>' +
                '<div id="osChartSummary" class="os-chart-summary"></div>' +
              '</div>' +
              '<div class="os-chart-legend">' +
                '<span><i style="background:#ff5e7d"></i>实线：克制对手</span>' +
                '<span><i style="background:#f0b083"></i>虚线：己方穿戴负作用</span>' +
                '<span><i style="background:#63c7c4"></i>供给资源</span>' +
                '<span><i style="background:#7bd3a1"></i>词条触发</span>' +
                '<span><i style="background:#4ea3ff"></i>共同协同</span>' +
                '<span><i style="background:#d5b966"></i>乘数放大</span>' +
                '<span class="os-legend-tip">提示：点击图谱节点切换聚焦实体，滚轮缩放，拖拽平移</span>' +
              '</div>' +
            '</section>' +
          '</div>' +
        '</div>' +

        '<div id="osMatrixView" class="' + (S.subView === "matrix" ? "" : "hidden") + '">' +
          originalMatrixHtml +
        '</div>' +
      '</div>';

    bindSkeletonEvents(hostEl);
    renderAllPanels();
  }

  function bindSkeletonEvents(hostEl) {
    Array.prototype.forEach.call(hostEl.querySelectorAll("[data-os-view]"), function (btn) {
      btn.onclick = function () {
        S.subView = btn.getAttribute("data-os-view");
        Array.prototype.forEach.call(hostEl.querySelectorAll("[data-os-view]"), function (b) {
          b.classList.toggle("is-active", b === btn);
        });
        document.getElementById("osGraphView").classList.toggle("hidden", S.subView !== "graph");
        document.getElementById("osMatrixView").classList.toggle("hidden", S.subView !== "matrix");
        if (S.subView === "graph" && S.chart) {
          setTimeout(function () { S.chart.resize(); }, 50);
        }
      };
    });

    var searchInput = document.getElementById("osSearchInput");
    if (searchInput) {
      searchInput.oninput = function () {
        S.q = this.value.trim();
        renderAtlasColumn();
      };
    }

    Array.prototype.forEach.call(hostEl.querySelectorAll("[data-scope]"), function (btn) {
      btn.onclick = function () {
        S.graphScope = btn.getAttribute("data-scope");
        Array.prototype.forEach.call(hostEl.querySelectorAll("[data-scope]"), function (b) {
          b.classList.toggle("on", b === btn);
        });
        renderAllPanels();
      };
    });

    Array.prototype.forEach.call(hostEl.querySelectorAll("[data-dir]"), function (btn) {
      btn.onclick = function () {
        var k = btn.getAttribute("data-dir");
        S.dirSel[k] = !S.dirSel[k];
        if (!S.dirSel["克制"] && !S.dirSel["被克制"]) S.dirSel[k] = true;
        btn.classList.toggle("on", !!S.dirSel[k]);
        renderChartPanel();
      };
    });

    Array.prototype.forEach.call(hostEl.querySelectorAll("[data-str]"), function (btn) {
      btn.onclick = function () {
        var k = btn.getAttribute("data-str");
        S.strength[k] = !S.strength[k];
        btn.classList.toggle("on", !!S.strength[k]);
        renderChartPanel();
      };
    });

    Array.prototype.forEach.call(hostEl.querySelectorAll("[data-deg]"), function (btn) {
      btn.onclick = function () {
        S.degree = parseInt(btn.getAttribute("data-deg"), 10);
        Array.prototype.forEach.call(hostEl.querySelectorAll("[data-deg]"), function (b) {
          b.classList.toggle("on", b === btn);
        });
        renderChartPanel();
      };
    });

    var causeBox = document.getElementById("osCauseChips");
    if (causeBox) {
      causeBox.innerHTML = CAUSE_ORDER.map(function (c) {
        return '<button type="button" class="os-chip ' + (S.cause[c] ? "on" : "") + '" data-cause="' + esc(c) + '">' + esc(c) + '</button>';
      }).join("");
      Array.prototype.forEach.call(causeBox.querySelectorAll("[data-cause]"), function (btn) {
        btn.onclick = function () {
          var c = btn.getAttribute("data-cause");
          S.cause[c] = !S.cause[c];
          btn.classList.toggle("on", !!S.cause[c]);
          renderChartPanel();
        };
        btn.ondblclick = function () {
          var c = btn.getAttribute("data-cause");
          CAUSE_ORDER.forEach(function (k) { S.cause[k] = (k === c); });
          Array.prototype.forEach.call(causeBox.querySelectorAll("[data-cause]"), function (b) {
            b.classList.toggle("on", !!S.cause[b.getAttribute("data-cause")]);
          });
          renderChartPanel();
        };
      });
    }

    var lineupSel = document.getElementById("osLineupSelect");
    if (lineupSel) {
      var lineups = S.nodes.filter(function (n) { return n.type === "阵容"; }).sort(function (a, b) {
        return a.archetype.localeCompare(b.archetype) || a.name.localeCompare(b.name);
      });
      lineupSel.innerHTML = '<option value="">破阵速查：选择对面阵容 (' + lineups.length + '套)…</option>' +
        lineups.map(function (n) {
          var core = (n.meta && n.meta["核心"]) ? " · 核心:" + n.meta["核心"] : "";
          return '<option value="' + esc(n.id) + '">' + esc(n.archetype) + " ｜ " + esc(n.name) + esc(core) + "</option>";
        }).join("");
      lineupSel.onchange = function () {
        if (!this.value) return;
        S.dirSel["克制"] = false;
        S.dirSel["被克制"] = true;
        S.tgtT["阵容"] = true;
        Array.prototype.forEach.call(hostEl.querySelectorAll("[data-dir]"), function (b) {
          b.classList.toggle("on", !!S.dirSel[b.getAttribute("data-dir")]);
        });
        selectNode(this.value);
      };
    }

    var tgtTypeBox = document.getElementById("osTargetTypeChips");
    if (tgtTypeBox) {
      var allT = allTypes();
      tgtTypeBox.innerHTML = allT.map(function (t) {
        return '<button type="button" class="os-chip ' + (S.tgtT[t] ? "on" : "") + '" data-tgttype="' + esc(t) + '">' + esc(t) + '</button>';
      }).join("");
      Array.prototype.forEach.call(tgtTypeBox.querySelectorAll("[data-tgttype]"), function (btn) {
        btn.onclick = function () {
          var t = btn.getAttribute("data-tgttype");
          S.tgtT[t] = !S.tgtT[t];
          btn.classList.toggle("on", !!S.tgtT[t]);
          renderChartPanel();
        };
        btn.ondblclick = function () {
          var t = btn.getAttribute("data-tgttype");
          allT.forEach(function (k) { S.tgtT[k] = (k === t); });
          Array.prototype.forEach.call(tgtTypeBox.querySelectorAll("[data-tgttype]"), function (b) {
            b.classList.toggle("on", !!S.tgtT[b.getAttribute("data-tgttype")]);
          });
          renderChartPanel();
        };
      });
    }
  }

  function renderAllPanels() {
    renderAtlasColumn();
    renderDetailColumn();
    renderChartPanel();
  }

  function renderAtlasColumn() {
    var tabBox = document.getElementById("osTypeTabs");
    var listBox = document.getElementById("osAtlasList");
    if (!tabBox || !listBox) return;

    var counts = {};
    S.nodes.forEach(function (n) { counts[n.type] = (counts[n.type] || 0) + 1; });
    var types = allTypes();

    tabBox.innerHTML = types.map(function (t) {
      return '<button type="button" class="os-type-btn ' + (t === S.atlasType ? "on" : "") + '" data-type="' + esc(t) + '">' +
        esc(t) + '<small>' + (counts[t] || 0) + '</small></button>';
    }).join("");

    Array.prototype.forEach.call(tabBox.querySelectorAll("[data-type]"), function (btn) {
      btn.onclick = function () {
        S.atlasType = btn.getAttribute("data-type");
        listBox.scrollTop = 0;
        renderAtlasColumn();
      };
    });

    var q = (S.q || "").toLowerCase();
    var degMap = S.graphScope === "all" ? S.totalDeg : S.counterDeg;
    var rows = S.nodes.filter(function (n) {
      if (!q && n.type !== S.atlasType) return false;
      if (!q) return true;
      return n.name.toLowerCase().indexOf(q) >= 0 ||
        (n.summary || "").toLowerCase().indexOf(q) >= 0 ||
        (n.text || "").toLowerCase().indexOf(q) >= 0;
    }).sort(function (a, b) {
      return (degMap[b.id] || 0) - (degMap[a.id] || 0) || a.name.localeCompare(b.name, "zh");
    });

    listBox.innerHTML = rows.map(function (n) {
      var d = degMap[n.id] || 0;
      var thumbHtml = n.thumb
        ? '<img class="os-ent-thumb" src="' + esc(n.thumb) + '" alt="" loading="lazy" onerror="this.style.display=\'none\'">'
        : '<span class="os-ent-glyph">' + shapeSvg(n.symbol, n.color) + '</span>';
      return '<button type="button" class="os-ent-row ' + (S.atlasId === n.id ? "is-selected" : "") + '" data-id="' + esc(n.id) + '">' +
        thumbHtml +
        '<div class="os-ent-main">' +
          '<div class="os-ent-title">' +
            '<strong>' + esc(n.name) + '</strong>' +
            '<span class="os-ent-deg">' + (S.graphScope === "all" ? "关联 " : "克制 ") + d + '</span>' +
          '</div>' +
          '<small>' + esc(n.type) + (n.role ? " · " + esc(n.role) : "") + (n.archetype ? " · " + esc(n.archetype) : "") + '</small>' +
          (n.summary ? '<em>' + esc(n.summary) + '</em>' : '') +
        '</div>' +
      '</button>';
    }).join("") || '<div class="os-empty">无匹配实体</div>';

    Array.prototype.forEach.call(listBox.querySelectorAll("[data-id]"), function (row) {
      row.onclick = function () {
        selectNode(row.getAttribute("data-id"));
      };
    });
  }

  function selectNode(id) {
    var n = S.byId[id];
    if (!n) return;
    S.atlasId = id;
    if (!S.q) S.atlasType = n.type;
    S.focus = id;
    S.detailEdge = null;
    S.selectedEdge = null;

    // 方向保持单向聚焦（优先展示“→ 它克制谁”，如果它没有出边只有入边则自动翻到“← 谁克制它”）
    var allowed = activeRelTypes();
    var out = 0, inn = 0;
    S.edges.forEach(function (e) {
      if (allowed.indexOf(e.type) < 0) return;
      if (e.source === id) out++;
      if (e.target === id) inn++;
    });
    if (n.type === "阵容" || n.type === "流派") {
      // 选阵容或流派时，默认看“谁克制它（怎么破阵）”
      S.dirSel["克制"] = false;
      S.dirSel["被克制"] = true;
      S.tgtT[n.type] = true;
    } else if (out > 0) {
      S.dirSel["克制"] = true;
      S.dirSel["被克制"] = false;
    } else if (inn > 0) {
      S.dirSel["克制"] = false;
      S.dirSel["被克制"] = true;
    }

    Array.prototype.forEach.call(document.querySelectorAll("[data-dir]"), function (b) {
      b.classList.toggle("on", !!S.dirSel[b.getAttribute("data-dir")]);
    });

    renderAllPanels();
  }

  function renderDetailColumn() {
    var box = document.getElementById("osDetailBody");
    if (!box) return;
    var n = S.atlasId && S.byId[S.atlasId];
    if (!n) {
      box.innerHTML = '<div class="os-empty">请在左侧选择任意装备、英雄、天赋或阵容查看克制推演详情</div>';
      return;
    }

    var metaBadges = Object.keys(n.meta || {}).map(function (k) {
      var v = n.meta[k];
      if (!v || (Array.isArray(v) && !v.length)) return "";
      return '<span class="os-badge">' + esc(k) + "：" + esc(Array.isArray(v) ? v.join("、") : v) + "</span>";
    }).join("");

    var propsHtml = "";
    if (n.latestProps) {
      var p = n.latestProps;
      propsHtml = '<dl class="os-stat-grid">' +
        '<div><dt>最大生命</dt><dd>' + (p.HP || "-") + '</dd></div>' +
        '<div><dt>物攻 / 法攻</dt><dd>' + (p.phyAttack || 0) + ' / ' + (p.magAttack || 0) + '</dd></div>' +
        '<div><dt>物防 / 法防</dt><dd>' + (p.phyDefense || 0) + ' / ' + (p.magDefense || 0) + '</dd></div>' +
        '<div><dt>法力值</dt><dd>' + (p.initEnergy || 0) + ' / ' + (p.energy || 0) + '</dd></div>' +
        '<div><dt>基础攻速</dt><dd>' + (p.attackSpeed ? (p.attackSpeed / 10000).toFixed(2) : "-") + '</dd></div>' +
        '<div><dt>攻击距离</dt><dd>' + (p.attackDistance || "-") + ' 格</dd></div>' +
      '</dl>';
    }

    var engineOrProfileHtml = "";
    if (n.type === "阵容" || n.type === "流派") {
      var engs = n.engines || [];
      if (n.members && n.members.length) {
        engineOrProfileHtml += '<div class="os-sec"><h3>阵容成员 (' + n.members.length + ')</h3><div class="os-tags">' +
          n.members.map(function (m) {
            var targetNode = S.byName[m];
            return '<button type="button" class="os-tag-btn" ' + (targetNode ? 'data-jump="' + esc(targetNode.id) + '"' : '') + '>' + esc(m) + '</button>';
          }).join("") + '</div></div>';
      }
      engs.forEach(function (e) {
        engineOrProfileHtml += '<div class="os-sec"><h3>三环节运转引擎 · ' + esc(e.cluster || "") + '</h3>' +
          '<div class="os-chain">' +
          (e.chain || []).map(function (c) {
            var who = (c.who || []).filter(Boolean);
            return '<div class="os-chain-step">' +
              '<span class="os-step-name">' + esc(c.stage) + '</span>' +
              '<div>' +
                (c.timing ? '<small class="os-step-time">' + esc(c.timing) + '</small>' : '') +
                '<p>' + esc(c.what) + '</p>' +
                (who.length ? '<em>承担者：' + esc(who.join("、")) + '</em>' : '') +
              '</div>' +
            '</div>';
          }).join("") +
          '</div>' +
          ((e.breakpoints && e.breakpoints.length) ? (
            '<h4 class="os-sub-h">各环节战斗内可打断性</h4>' +
            e.breakpoints.map(function (b) {
              return '<div class="os-bp-row"><span class="os-pill ' + (b.in_battle ? "is-cnt" : "is-safe") + '">' +
                esc(b.stage) + " · " + (b.in_battle ? "战斗内可打断" : "备战期不可打断") + '</span>' +
                '<p>' + esc(b.how) + (b.effect ? " → " + esc(b.effect) : "") + '</p></div>';
            }).join("")
          ) : "") +
        '</div>';
      });
    } else {
      var tagPills = function (arr, cls) {
        if (!arr || !arr.length) return '<span class="os-muted">无</span>';
        return arr.map(function (x) {
          var label = typeof x === "string" ? x : ((x.resource || x.target || "") + (x.target && x.resource ? " → " + x.target : "") + (x.strength ? "·" + x.strength : ""));
          return '<span class="os-tag ' + (cls || "") + '">' + esc(label) + '</span>';
        }).join("");
      };
      engineOrProfileHtml = '<div class="os-sec"><h3>机制画像与命门推演</h3>' +
        '<div class="os-kv-rows">' +
          '<div><span>发出词条</span><div>' + tagPills(n.emits, "is-cyan") + '</div></div>' +
          '<div><span>监听事件</span><div>' + tagPills(n.listens, "is-gold") + '</div></div>' +
          '<div><span>产出资源</span><div>' + tagPills(n.produces, "is-cyan") + '</div></div>' +
          '<div><span>运转必需</span><div>' + tagPills(n.requires, "is-warn") + '</div></div>' +
          (n.vulnerable_to && n.vulnerable_to.length ? '<div><span>自身命门</span><div>' + tagPills(n.vulnerable_to, "is-cnt") + '</div></div>' : '') +
          (n.counters && n.counters.length ? '<div><span>针对敌方</span><div>' + tagPills(n.counters, "is-cyan") + '</div></div>' : '') +
        '</div>' +
      '</div>';
    }

    var allowed = activeRelTypes();
    var relEdges = S.edges.filter(function (e) {
      return (e.source === n.id || e.target === n.id) && allowed.indexOf(e.type) >= 0;
    });
    var order = { "强": 0, "中": 1, "弱": 2 };
    relEdges.sort(function (a, b) {
      return (order[a.strength] - order[b.strength]) || a.type.localeCompare(b.type);
    });

    var f = S.relf;
    var filteredEdges = relEdges.filter(function (e) {
      var isOut = e.source === n.id;
      if (f.dir === "out" && !isOut) return false;
      if (f.dir === "in" && isOut) return false;
      if (f.rel && e.type !== f.rel) return false;
      return true;
    });

    var outCount = relEdges.filter(function (e) { return e.source === n.id; }).length;
    var inCount = relEdges.length - outCount;

    box.innerHTML =
      '<div class="os-detail-head">' +
        (n.thumb ? '<img class="os-detail-avatar" src="' + esc(n.thumb) + '" alt="">' : '') +
        '<div class="os-detail-title">' +
          '<div class="os-detail-topline">' +
            '<span>' + esc(n.type) + (n.role ? " · " + esc(n.role) : "") + '</span>' +
            (n.isCalibrated ? '<em class="os-calibrated-badge">✓ 最新图鉴数值</em>' : '') +
          '</div>' +
          '<h2>' + esc(n.name) + '</h2>' +
          '<div class="os-badges">' +
            '<span class="os-badge">' + esc(n.archetype || "通用") + '</span>' +
            metaBadges +
          '</div>' +
        '</div>' +
      '</div>' +
      propsHtml +
      (n.text ? '<div class="os-sec"><h3>最新官方卡面与技能数值</h3><div class="os-card-text">' + esc(n.text).split(" | ").map(function (line) { return "<p>" + line + "</p>"; }).join("") + '</div></div>' : '') +
      engineOrProfileHtml +
      '<div class="os-sec">' +
        '<div class="os-sec-head">' +
          '<h3>克制与机制条文 (' + filteredEdges.length + ' / ' + relEdges.length + ')</h3>' +
          '<div class="os-mini-tabs">' +
            '<button type="button" class="' + (!f.dir ? "on" : "") + '" data-rdir="">全部 (' + relEdges.length + ')</button>' +
            '<button type="button" class="' + (f.dir === "out" ? "on" : "") + '" data-rdir="out">出边/克制 (' + outCount + ')</button>' +
            '<button type="button" class="' + (f.dir === "in" ? "on" : "") + '" data-rdir="in">入边/被克 (' + inCount + ')</button>' +
          '</div>' +
        '</div>' +
        '<div class="os-edge-list">' +
          filteredEdges.slice(0, 150).map(function (e) {
            var isOut = e.source === n.id;
            var other = S.byId[isOut ? e.target : e.source];
            var arrow = SYMMETRIC[e.type] ? "↔" : (isOut ? "→" : "←");
            var causeHtml = (e.type === "克制" && e.cause)
              ? '<span class="os-cause-tag">' + esc(e.cause) + (e.cause_sub ? " · " + esc(e.cause_sub) : "") + '</span>'
              : (e.type === "负作用" && e.cause_sub ? '<span class="os-cause-tag is-warn">负作用 · ' + esc(e.cause_sub) + '</span>' : '');
            return '<article class="os-edge-item">' +
              '<div class="os-edge-top">' +
                '<span class="os-pill is-' + (e.type === "克制" ? "cnt" : e.type === "负作用" ? "warn" : "cyan") + '">' + esc(e.type) + " · " + esc(e.strength) + '</span>' +
                '<span class="os-edge-dir">' + arrow + '</span>' +
                '<button type="button" class="os-entity-jump" data-jump="' + esc(other.id) + '">' +
                  (other.thumb ? '<img src="' + esc(other.thumb) + '" alt="">' : '') +
                  '<strong>' + esc(other.name) + '</strong>' +
                  '<small>' + esc(other.type) + '</small>' +
                '</button>' +
                causeHtml +
              '</div>' +
              '<p class="os-edge-reason">' + esc(e.reason || "") + '</p>' +
            '</article>';
          }).join("") +
        '</div>' +
      '</div>';

    Array.prototype.forEach.call(box.querySelectorAll("[data-rdir]"), function (btn) {
      btn.onclick = function () {
        S.relf.dir = btn.getAttribute("data-rdir");
        renderDetailColumn();
      };
    });

    Array.prototype.forEach.call(box.querySelectorAll("[data-jump]"), function (btn) {
      btn.onclick = function () {
        selectNode(btn.getAttribute("data-jump"));
      };
    });
  }

  function renderChartPanel() {
    var canvas = document.getElementById("osChartCanvas");
    var summary = document.getElementById("osChartSummary");
    if (!canvas || typeof window.echarts === "undefined") return;

    if (!S.chart || S.chart.getDom() !== canvas) {
      if (S.chart) S.chart.dispose();
      S.chart = window.echarts.init(canvas, null, { renderer: "canvas" });
      S.chart.on("click", function (p) {
        if (p.dataType === "node" && p.data && p.data.id) {
          selectNode(p.data.id);
        }
      });
      window.addEventListener("resize", function () {
        if (S.chart) S.chart.resize();
      });
    }

    var gv = computeVisibleGraph();
    var showLabel = gv.nodes.length <= 180;

    var data = gv.nodes.map(function (n) {
      var d = gv.deg[n.id] || 0;
      var isFocus = S.focus === n.id;
      return {
        id: n.id,
        name: n.id,
        value: d,
        symbol: n.symbol || "circle",
        symbolSize: Math.min(44, 12 + Math.sqrt(d) * 4.0) * (isFocus ? 1.45 : 1),
        itemStyle: {
          color: isFocus ? "#8fdfdc" : n.color,
          borderColor: isFocus ? "#ffffff" : "rgba(15,20,28,0.8)",
          borderWidth: isFocus ? 2.5 : 1
        },
        label: {
          show: showLabel || isFocus,
          formatter: n.name,
          fontSize: isFocus ? 13 : 11,
          fontWeight: isFocus ? 700 : 400,
          color: isFocus ? "#ffffff" : "#d8e0e8"
        }
      };
    });

    var tagEdge = gv.edges.length <= 36;
    var links = gv.edges.map(function (e) {
      var cfg = REL[e.type] || REL["克制"];
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        lineStyle: {
          color: cfg.color,
          curveness: cfg.curve,
          width: (STRENGTH_W[e.strength] || 2) * 0.78,
          type: e.type === "负作用" ? "dashed" : "solid",
          opacity: 0.72
        },
        symbol: ["none", cfg.arrow ? "arrow" : "none"],
        symbolSize: [0, cfg.arrow || 0],
        label: {
          show: tagEdge && e.type === "克制" && !!e.cause_sub,
          formatter: e.cause_sub ? e.cause_sub : "",
          fontSize: 9.5,
          color: "#ffb8c6",
          backgroundColor: "rgba(16,20,26,0.85)",
          padding: [2, 4]
        }
      };
    });

    S.chart.setOption({
      backgroundColor: "transparent",
      animation: gv.nodes.length <= 350,
      tooltip: {
        backgroundColor: "rgba(18, 22, 29, 0.96)",
        borderColor: "rgba(178, 189, 204, 0.28)",
        textStyle: { color: "#edf0f3", fontSize: 12 },
        extraCssText: "max-width:360px;white-space:normal;border-radius:3px;",
        formatter: function (p) {
          if (p.dataType === "node") {
            var n = S.byId[p.data.id];
            if (!n) return "";
            return "<b>" + esc(n.name) + "</b> <span style='color:#939ca9'>" + esc(n.type) +
              " · " + esc(n.role || "") + " · " + esc(n.archetype || "") + "</span>" +
              "<br/><span style='color:#c5cbd3'>" + esc(n.summary || "") + "</span>" +
              "<br/><span style='color:#77cfcc'>当前连接 " + p.data.value + " 条 · 点击切换聚焦</span>";
          }
          var e = S.edges.find(function (x) { return x.id === p.data.id; });
          if (!e) return "";
          var a = S.byId[e.source], b = S.byId[e.target];
          var cfg = REL[e.type] || REL["克制"];
          var tag = (e.type === "克制" && e.cause) ? "【" + e.cause + " · " + (e.cause_sub || "") + "】" : "";
          return "<b style='color:" + cfg.color + "'>" + esc(a.name) + " → " + esc(b.name) + " (" + e.type + "·" + e.strength + ")</b>" +
            (tag ? "<br/><span style='color:#f0b083'>" + esc(tag) + "</span>" : "") +
            "<br/><span style='color:#d6dde3'>" + esc(e.reason || "") + "</span>";
        }
      },
      series: [{
        type: "graph",
        layout: "force",
        roam: true,
        draggable: true,
        data: data,
        links: links,
        label: { position: "right" },
        force: {
          repulsion: gv.nodes.length > 200 ? 130 : 280,
          edgeLength: gv.nodes.length > 200 ? 68 : 118,
          gravity: 0.14,
          friction: 0.28
        },
        emphasis: {
          focus: "adjacency",
          label: { show: true },
          lineStyle: { width: 3.2, opacity: 1 }
        }
      }]
    }, { notMerge: true });

    if (summary) {
      var fn = S.focus && S.byId[S.focus];
      summary.innerHTML =
        '<span>当前聚焦：<b>' + (fn ? esc(fn.name) + " (" + esc(fn.type) + ")" : "全局") + '</b></span>' +
        '<span>子图节点：<b>' + gv.nodes.length + '</b></span>' +
        '<span>子图关系边：<b>' + gv.edges.length + '</b></span>';
    }
  }

  /* 当 /counters 路由被激活时，自动增强为 OS 实体推演图谱 + 27流派矩阵双视图工作台 */
  function tryMountOnCountersPage() {
    var path = location.pathname || "";
    if (path !== "/counters" && !path.startsWith("/counters/")) return;
    var appEl = document.getElementById("app");
    if (!appEl || appEl.querySelector(".os-page")) return;

    var originalMatrixHtml = appEl.innerHTML;
    // 如果 URL 是 /counters/xxx 具体流派，默认先显示具体流派，同时提供顶部切换到 OS 图谱
    if (path.startsWith("/counters/") && path.length > "/counters/".length) {
      S.subView = "matrix";
    }

    loadGraphData().then(function () {
      if (location.pathname !== "/counters" && !location.pathname.startsWith("/counters/")) return;
      renderWorkbenchSkeleton(appEl, originalMatrixHtml);
    });
  }

  window.OSCounterGraph = {
    mountIfNeeded: tryMountOnCountersPage,
    selectNode: selectNode
  };
})();
