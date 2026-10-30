/* 万象棋 · 个人实战阵容笔记工作台 (74篇深度阵容笔记 + 157张本地实战截图 + 图鉴实体自动联动) */
(function () {
  var State = {
    loaded: false,
    loading: false,
    subView: "notes", // "notes" (74篇个人实战阵容笔记) | "community" (4266套社区阵容库)
    notes: [],
    activeIdx: 0,
    q: "",
    tagFilter: "",
    entRegex: null,
    entMap: null
  };

  var QUICK_TAGS = ["全部", "三分", "日落海", "大河", "河洛", "逐鹿", "无阵营", "花木兰", "艾琳", "李信", "韩信", "嬴政", "炸盾", "养猪", "蒙恬", "诸葛亮"];

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c];
    });
  }

  function loadNotesData() {
    if (State.loaded) return Promise.resolve();
    if (State.loading) return State.loadingPromise;
    State.loading = true;
    State.loadingPromise = fetch("/content/wecom_notes.json")
      .then(function (r) { return r.json(); })
      .then(function (list) {
        State.notes = (list || []).map(function (item, idx) {
          var imgCount = 0;
          var textSnippets = [];
          function walk(blocks) {
            (blocks || []).forEach(function (b) {
              if (b.img) imgCount++;
              if (b.text) textSnippets.push(b.text);
              if (b.children) walk(b.children);
            });
          }
          walk(item.blocks);
          var fullText = item.title + " " + textSnippets.join(" ");
          var displayTitle = item.title === "wan" ? "综合倒转总纲（三分 / 逐鹿嬴政 / 日落海）" : item.title;
          return {
            idx: idx,
            id: item.id,
            title: displayTitle,
            rawTitle: item.title,
            blocks: item.blocks || [],
            imgCount: imgCount,
            paragraphCount: textSnippets.length,
            searchText: fullText.toLowerCase(),
            summary: textSnippets.slice(0, 2).join(" · ").slice(0, 90)
          };
        });
        State.loaded = true;
        State.loading = false;
      });
    return State.loadingPromise;
  }

  /* 构建图鉴实体词典，把笔记里的英雄、装备、天赋、效果牌、棋手自动转为可悬浮/可点击的 .ent 标签 */
  function ensureEntityMatcher() {
    if (State.entRegex) return;
    var wxqData = (window.App && window.App.state && window.App.state.data) ? window.App.state.data : null;
    if (!wxqData) return;

    var map = new Map();
    function add(name, type, id, thumb) {
      if (!name || name.length < 2) return;
      if (!map.has(name)) {
        map.set(name, { type: type, id: id, thumb: thumb || "" });
      }
    }

    (wxqData.heroes || []).forEach(function (h) { add(h.name, "hero", h.id, h.thumb); });
    (wxqData.lords || []).forEach(function (l) { add(l.name, "lord", l.id, l.icon); });
    (wxqData.equips || []).forEach(function (eq) {
      add(eq.name, "equip", eq.id, eq.thumb);
      if (eq.name && eq.name.indexOf("·") > 0) {
        add(eq.name.split("·")[0], "equip", eq.id, eq.thumb);
      }
    });
    (wxqData.talents || []).forEach(function (t) { add(t.name, "talent", t.id, t.thumb); });
    (wxqData.effects || []).forEach(function (ef) { add(ef.name, "effect", ef.id, ef.thumb); });

    // 补充玩家高频简称映射
    var aliases = {
      "阿珂": "阿轲",
      "白鸽": "白歌",
      "赢律": "嬴律",
      "常小鹅": "常小娥",
      "嫦娥": "常小娥",
      "小明": "明世隐",
      "鲁大": "鲁班大师",
      "守约": "百里守约",
      "玄策": "百里玄策",
      "干将": "干将莫邪",
      "婉儿": "上官婉儿",
      "元芳": "李元芳",
      "大乔": "大乔",
      "小乔": "小乔",
      "老虎": "裴擒虎",
      "牢大": "司空震",
      "司空": "司空震",
      "反甲": "反伤重甲",
      "魔女": "魔女斗篷",
      "冰心": "极寒风暴",
      "冰矛": "寒霜侵袭",
      "炽热": "炽热支配者",
      "苍穹": "纯净苍穹",
      "扶摇": "扶摇直上"
    };
    Object.keys(aliases).forEach(function (shortName) {
      var target = map.get(aliases[shortName]);
      if (target && !map.has(shortName)) {
        map.set(shortName, target);
      }
    });

    var keys = Array.from(map.keys()).sort(function (a, b) { return b.length - a.length; });
    if (!keys.length) return;
    var pattern = keys.map(function (k) {
      return k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }).join("|");
    State.entMap = map;
    State.entRegex = new RegExp(pattern, "g");
  }

  function findCoverAvatar(note) {
    ensureEntityMatcher();
    if (!State.entMap || !State.entRegex) return "";
    var m = (note.title + " " + note.summary).match(State.entRegex);
    if (m) {
      for (var i = 0; i < m.length; i++) {
        var info = State.entMap.get(m[i]);
        if (info && info.thumb && (info.type === "hero" || info.type === "lord")) {
          return info.thumb;
        }
      }
      var firstInfo = State.entMap.get(m[0]);
      if (firstInfo && firstInfo.thumb) return firstInfo.thumb;
    }
    return "/images/game-os-cos_custom_os_hero_touxiang_auto_2271ca2d7d8a6420d326c3fa336b9ac7.png";
  }

  function renderRichEntities(text) {
    var safe = esc(text || "");
    ensureEntityMatcher();
    if (!State.entRegex || !State.entMap) return safe;
    return safe.replace(State.entRegex, function (match) {
      var info = State.entMap.get(match);
      if (!info) return match;
      return '<span class="ent ent-' + info.type + '" data-type="' + info.type + '" data-id="' + info.id + '">' + match + '</span>';
    });
  }

  function renderBlocksToMarkdownHtml(blocks) {
    if (!blocks || !blocks.length) {
      return '<div class="wn-empty-note">该篇笔记标题本身即为核心口诀要点（详见上方标题栏）。</div>';
    }
    var html = [];
    blocks.forEach(function (b) {
      if (b.img) {
        html.push(
          '<figure class="wn-figure">' +
            '<div class="wn-img-wrap" data-zoom="' + esc(b.img) + '">' +
              '<img src="' + esc(b.img) + '" alt="阵容实战笔记配图" loading="lazy">' +
              '<span class="wn-zoom-hint">点击放大查看原图</span>' +
            '</div>' +
            (b.text ? '<figcaption>' + renderRichEntities(b.text) + '</figcaption>' : '') +
          '</figure>'
        );
      } else if (b.text) {
        var t = b.type || "text";
        if (t === "header1" || t === "header") {
          html.push('<h3 class="wn-h1">' + renderRichEntities(b.text) + '</h3>');
        } else if (t === "header2" || t === "sub_header") {
          html.push('<h4 class="wn-h2">' + renderRichEntities(b.text) + '</h4>');
        } else if (t === "header3" || t === "sub_sub_header") {
          html.push('<h5 class="wn-h3">' + renderRichEntities(b.text) + '</h5>');
        } else if (t === "bulleted_list" || t === "numbered_list") {
          html.push('<div class="wn-list-item"><span class="wn-bullet">◆</span><div>' + renderRichEntities(b.text) + '</div></div>');
        } else if (t === "quote" || t === "callout") {
          html.push('<blockquote class="wn-quote">' + renderRichEntities(b.text) + '</blockquote>');
        } else {
          // 如果短行像小标题（如“三分倒转”、“高阶逐鹿嬴政”、“日落海倒转”），渲染为分节小标题
          if (b.text.length <= 14 && !/[，。！？、,.!?]/.test(b.text)) {
            html.push('<h4 class="wn-section-tag">' + renderRichEntities(b.text) + '</h4>');
          } else {
            html.push('<p class="wn-p">' + renderRichEntities(b.text) + '</p>');
          }
        }
      }
      if (b.children && b.children.length) {
        html.push('<div class="wn-nested">' + renderBlocksToMarkdownHtml(b.children) + '</div>');
      }
    });
    return html.join("");
  }

  function renderNotesWorkbench(hostEl) {
    if (!hostEl) return;
    var existingWrap = document.getElementById("wnWorkbenchWrap");
    if (!existingWrap) {
      // 将原有的 4266 套社区阵容包装进 #wnCommunityView，并在顶部插入双模式切换栏
      var originalChildren = Array.from(hostEl.childNodes);
      var communityContainer = document.createElement("div");
      communityContainer.id = "wnCommunityView";
      communityContainer.className = State.subView === "community" ? "" : "hidden";
      originalChildren.forEach(function (ch) {
        communityContainer.appendChild(ch);
      });

      var headerBar = document.createElement("div");
      headerBar.id = "wnWorkbenchWrap";
      headerBar.innerHTML =
        '<div class="os-head" style="margin-bottom:10px">' +
          '<div>' +
            '<p class="os-eyebrow">LINEUP PLAYBOOK & ARCHIVE // PERSONAL WECOM NOTES MERGED</p>' +
            '<h1>万象棋实战阵容笔记 & 社区阵容库</h1>' +
            '<p class="os-sub">融合你精心制作的 74 篇企业微信万象棋实战阵容笔记（含 157 张实战对局截图）与 4,266 套社区推荐阵容。笔记内所有英雄/装备/天赋词条均支持悬浮查卡面。</p>' +
          '</div>' +
          '<div class="os-metrics">' +
            '<div class="os-metric"><span>个人实战笔记</span><strong>74 篇</strong><small>企微文档全量同步</small></div>' +
            '<div class="os-metric"><span>实战对局配图</span><strong>157 张</strong><small>高清原图已本地化</small></div>' +
            '<div class="os-metric"><span>社区阵容库</span><strong>4,266 套</strong><small>营地推荐与热门榜</small></div>' +
          '</div>' +
        '</div>' +
        '<div class="os-mode-bar">' +
          '<div class="os-mode-tabs">' +
            '<button type="button" class="os-mode-tab ' + (State.subView === "notes" ? "is-active" : "") + '" data-wn-view="notes">' +
              '实战阵容笔记 (74 篇图文笔记 · 157 张配图)' +
            '</button>' +
            '<button type="button" class="os-mode-tab ' + (State.subView === "community" ? "is-active" : "") + '" data-wn-view="community">' +
              '社区阵容库 (4,266 套营地阵容检索)' +
            '</button>' +
          '</div>' +
          '<span class="os-mode-status"><i></i><span>支持 Markdown 图文阅读 · 词条悬浮看卡面 · 点击图片全屏放大</span></span>' +
        '</div>' +
        '<div id="wnNotesView" class="' + (State.subView === "notes" ? "" : "hidden") + '">' +
          '<div class="wn-tag-bar" id="wnTagBar"></div>' +
          '<div class="wn-layout">' +
            '<aside class="wn-sidebar">' +
              '<div class="wn-search-wrap">' +
                '<input id="wnSearchInput" type="search" placeholder="搜索 74 篇笔记标题或正文关键词…" value="' + esc(State.q) + '">' +
              '</div>' +
              '<div class="wn-note-list" id="wnNoteList"></div>' +
            '</aside>' +
            '<article class="wn-reader" id="wnReader"></article>' +
          '</div>' +
        '</div>' +
        '<div id="wnLightbox" class="wn-lightbox hidden">' +
          '<button type="button" class="wn-lb-close" id="wnLbClose">✕</button>' +
          '<img id="wnLbImg" src="" alt="放大预览">' +
        '</div>';

      hostEl.appendChild(headerBar);
      hostEl.appendChild(communityContainer);

      // Hide duplicate page-head inside communityContainer
      var oldHead = communityContainer.querySelector(".page-head");
      if (oldHead) oldHead.style.display = "none";

      bindNotesEvents(hostEl);
    }

    renderTagBar();
    renderNoteSidebar();
    renderNoteArticle();
  }

  function bindNotesEvents(hostEl) {
    Array.prototype.forEach.call(hostEl.querySelectorAll("[data-wn-view]"), function (btn) {
      btn.onclick = function () {
        State.subView = btn.getAttribute("data-wn-view");
        Array.prototype.forEach.call(hostEl.querySelectorAll("[data-wn-view]"), function (b) {
          b.classList.toggle("is-active", b === btn);
        });
        document.getElementById("wnNotesView").classList.toggle("hidden", State.subView !== "notes");
        document.getElementById("wnCommunityView").classList.toggle("hidden", State.subView !== "community");
      };
    });

    var searchInput = document.getElementById("wnSearchInput");
    if (searchInput) {
      searchInput.oninput = function () {
        State.q = this.value.trim().toLowerCase();
        renderNoteSidebar();
      };
    }

    var lb = document.getElementById("wnLightbox");
    var lbClose = document.getElementById("wnLbClose");
    if (lb) {
      lb.onclick = function (e) {
        if (e.target === lb || e.target === lbClose) {
          lb.classList.add("hidden");
        }
      };
    }
  }

  function renderTagBar() {
    var box = document.getElementById("wnTagBar");
    if (!box) return;
    box.innerHTML = QUICK_TAGS.map(function (t) {
      var val = t === "全部" ? "" : t;
      return '<button type="button" class="chip ' + (State.tagFilter === val ? "on" : "") + '" data-wntag="' + esc(val) + '">' + esc(t) + '</button>';
    }).join("");
    Array.prototype.forEach.call(box.querySelectorAll("[data-wntag]"), function (btn) {
      btn.onclick = function () {
        State.tagFilter = btn.getAttribute("data-wntag");
        renderTagBar();
        renderNoteSidebar();
      };
    });
  }

  function filteredNotes() {
    return State.notes.filter(function (n) {
      if (State.tagFilter && n.searchText.indexOf(State.tagFilter.toLowerCase()) < 0) return false;
      if (State.q && n.searchText.indexOf(State.q) < 0) return false;
      return true;
    });
  }

  function renderNoteSidebar() {
    var listEl = document.getElementById("wnNoteList");
    if (!listEl) return;
    var list = filteredNotes();
    listEl.innerHTML = list.map(function (n) {
      var avatar = findCoverAvatar(n);
      return '<button type="button" class="wn-note-item ' + (State.activeIdx === n.idx ? "is-selected" : "") + '" data-idx="' + n.idx + '">' +
        '<img class="wn-note-avatar" src="' + esc(avatar) + '" alt="" loading="lazy">' +
        '<div class="wn-note-meta">' +
          '<div class="wn-note-title">' + esc(n.title) + '</div>' +
          '<div class="wn-note-sub">' +
            '<span>#' + (n.idx + 1) + '</span>' +
            (n.imgCount ? '<span class="wn-badge-img">' + n.imgCount + ' 图</span>' : '') +
            (n.paragraphCount ? '<span>' + n.paragraphCount + ' 段</span>' : '<span>口诀速记</span>') +
          '</div>' +
        '</div>' +
      '</button>';
    }).join("") || '<div class="os-empty" style="padding:24px;text-align:center;color:#939ca9">没有匹配的阵容笔记</div>';

    Array.prototype.forEach.call(listEl.querySelectorAll("[data-idx]"), function (btn) {
      btn.onclick = function () {
        State.activeIdx = parseInt(btn.getAttribute("data-idx"), 10);
        renderNoteSidebar();
        renderNoteArticle();
        var reader = document.getElementById("wnReader");
        if (reader) reader.scrollTop = 0;
      };
    });
  }

  function renderNoteArticle() {
    var reader = document.getElementById("wnReader");
    if (!reader) return;
    var note = State.notes[State.activeIdx] || State.notes[0];
    if (!note) return;

    var prevIdx = State.activeIdx > 0 ? State.activeIdx - 1 : null;
    var nextIdx = State.activeIdx < State.notes.length - 1 ? State.activeIdx + 1 : null;
    var avatar = findCoverAvatar(note);

    reader.innerHTML =
      '<header class="wn-article-head">' +
        '<div class="wn-article-title-row">' +
          '<img class="wn-article-avatar" src="' + esc(avatar) + '" alt="">' +
          '<div>' +
            '<div class="wn-article-kicker">实战阵容笔记 #' + (note.idx + 1) + ' / ' + State.notes.length +
              (note.imgCount ? ' · 含 ' + note.imgCount + ' 张实战截图' : '') +
            '</div>' +
            '<h2>' + renderRichEntities(note.title) + '</h2>' +
          '</div>' +
        '</div>' +
        '<div class="wn-nav-btns">' +
          '<button type="button" class="os-seg" ' + (prevIdx === null ? "disabled" : 'data-nav="' + prevIdx + '"') + '>← 上一篇</button>' +
          '<button type="button" class="os-seg" ' + (nextIdx === null ? "disabled" : 'data-nav="' + nextIdx + '"') + '>下一篇 →</button>' +
        '</div>' +
      '</header>' +
      '<div class="wn-md-body">' +
        renderBlocksToMarkdownHtml(note.blocks) +
      '</div>';

    Array.prototype.forEach.call(reader.querySelectorAll("[data-nav]"), function (btn) {
      btn.onclick = function () {
        State.activeIdx = parseInt(btn.getAttribute("data-nav"), 10);
        renderNoteSidebar();
        renderNoteArticle();
        reader.scrollTop = 0;
      };
    });

    Array.prototype.forEach.call(reader.querySelectorAll("[data-zoom]"), function (wrap) {
      wrap.onclick = function () {
        var src = wrap.getAttribute("data-zoom");
        var lb = document.getElementById("wnLightbox");
        var lbImg = document.getElementById("wnLbImg");
        if (lb && lbImg && src) {
          lbImg.src = src;
          lb.classList.remove("hidden");
        }
      };
    });
  }

  function tryMountOnLineupsPage() {
    var path = location.pathname || "";
    if (path !== "/lineups" && path !== "/wxq-lineups") return;
    var appEl = document.getElementById("app");
    if (!appEl || appEl.querySelector("#wnWorkbenchWrap")) return;

    loadNotesData().then(function () {
      var curPath = location.pathname || "";
      if (curPath !== "/lineups" && curPath !== "/wxq-lineups") return;
      renderNotesWorkbench(appEl);
    });
  }

  window.WeComLineupNotes = {
    mountIfNeeded: tryMountOnLineupsPage
  };
})();
