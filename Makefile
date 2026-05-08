# AI 志愿规划师 - 跨省数据更新自动化
#
# 用法:
#   make help                    # 查看帮助
#   make crawl PROV=hunan         # 爬该省录取数据(后台跑)
#   make crawl PROV=hunan FG=1    # 前台跑(看实时输出)
#   make update PROV=hunan        # 全套更新流程(crawl + 引导后续手动步骤)
#   make verify PROV=hunan        # 验证该省数据 + 脚本能跑
#
# 环境变量(可覆盖):
#   PROV: 省份拼音名(默认 hubei)
#   YEARS: 年份范围(默认 2021-2025)

PROV ?= hubei
YEARS ?= 2021-2025
ROOT := $(shell pwd)

# 省份名映射(中文标识,仅展示用)
PROV_ZH_hubei = 湖北
PROV_ZH_hunan = 湖南
PROV_ZH_jiangsu = 江苏
PROV_ZH_henan = 河南
PROV_ZH_guangdong = 广东
PROV_ZH_shandong = 山东
PROV_ZH_hebei = 河北
PROV_ZH_anhui = 安徽
PROV_ZH := $(PROV_ZH_$(PROV))


.PHONY: help
help:
	@echo "AI 志愿规划师 - 跨省自动化"
	@echo ""
	@echo "常用命令:"
	@echo "  make crawl PROV=<省>        # 爬该省录取数据(后台,约 3-4h)"
	@echo "  make crawl PROV=<省> FG=1    # 前台跑(看进度)"
	@echo "  make update PROV=<省>       # crawl + 后续步骤引导"
	@echo "  make verify PROV=<省>       # 验证数据 + 脚本能跑"
	@echo ""
	@echo "支持省份(31 选 1):"
	@echo "  hubei / hunan / hebei / liaoning / jiangsu / fujian / guangdong / chongqing"
	@echo "  henan / shanxi / sichuan / shaanxi / yunnan / ningxia / qinghai 等"
	@echo ""
	@echo "示例:"
	@echo "  make crawl PROV=hunan       # 启动湖南爬虫(后台)"
	@echo "  make verify PROV=hunan      # 看湖南数据情况"


.PHONY: crawl
crawl:
	@echo "=== 爬 $(PROV) ($(PROV_ZH)) 录取数据,年份 $(YEARS) ==="
ifeq ($(FG),1)
	python3 crawl.py --prov $(PROV) --years $(YEARS)
else
	@echo "(后台模式,日志写到 crawl_$(PROV).stdout.log)"
	@nohup python3 -W ignore crawl.py --prov $(PROV) --years $(YEARS) > crawl_$(PROV).stdout.log 2>&1 & \
		echo "PID=$$!"
	@echo "查看进度:tail -f crawl_$(PROV).stdout.log"
endif


.PHONY: update
update: crawl
	@echo ""
	@echo "✓ 爬虫已启动(后台,约 3-4 小时)"
	@echo ""
	@echo "═══════════════════════════════════════════════════════════"
	@echo "下一步(手动,等爬虫完成后):"
	@echo "═══════════════════════════════════════════════════════════"
	@echo ""
	@echo "1. 一分一段表 (data/yifenduyiduan/<年>_<科类>_$(PROV).csv)"
	@echo "   来源选项:"
	@echo "   a) GitHub: sdgedfegw/Gaokao-score-distribution(全国 1996-2024)"
	@echo "      git clone https://github.com/sdgedfegw/Gaokao-score-distribution /tmp/gskd"
	@echo "      过滤 省级行政区='$(PROV_ZH)' 提取"
	@echo "   b) 当年新数据:从 $(PROV_ZH) 招办官网抓 PDF"
	@echo ""
	@echo "2. 批次线 (data/batch_lines/$(PROV).csv)"
	@echo "   格式:年份,科类,批次,控制线分数,对应位次,数据来源"
	@echo "   位次从一分一段表反查"
	@echo ""
	@echo "3. 院校档案 (skill/$(PROV)-zhiyuan/references/20_院校潜规则_$(PROV_ZH)视角/<校>.md)"
	@echo "   每篇含:王牌/坑专业/录取分布/毕业出口/同档对比/卡片填充字段"
	@echo "   参考湖北:skill/hubei-zhiyuan/references/20_院校潜规则_湖北视角/武汉大学.md"
	@echo ""
	@echo "4. 本地化 (skill/$(PROV)-zhiyuan/references/90_$(PROV_ZH)本地化/)"
	@echo "   - 3+1+2政策.md(选科+院校专业组+志愿规则,本省特定)"
	@echo "   - $(PROV_ZH)强校真实地位.md(本省院校梯队 overview)"
	@echo ""
	@echo "5. 验证:make verify PROV=$(PROV)"


.PHONY: verify
verify:
	@echo "=== 验证 $(PROV) ($(PROV_ZH)) 数据完整性 ==="
	@echo ""
	@echo "[1] 录取数据库 data/gaokao_$(PROV)_*.db"
	@ls -la data/gaokao_$(PROV)_*.db 2>/dev/null || echo "  ❌ 不存在"
	@echo ""
	@echo "[2] 一分一段表 data/yifenduyiduan/*_$(PROV).csv"
	@ls data/yifenduyiduan/*_$(PROV).csv 2>/dev/null | wc -l | xargs echo "  CSV 文件数:"
	@echo ""
	@echo "[3] 批次线 data/batch_lines/$(PROV).csv"
	@[ -f data/batch_lines/$(PROV).csv ] && echo "  ✓ 存在 ($(shell wc -l < data/batch_lines/$(PROV).csv 2>/dev/null) 行)" || echo "  ❌ 不存在"
	@echo ""
	@echo "[4] Skill 目录 skill/$(PROV)-zhiyuan/"
	@[ -d skill/$(PROV)-zhiyuan ] && echo "  ✓ 存在" || echo "  ❌ 不存在"
	@echo ""
	@echo "[5] 跑 score_to_rank 测试(GAOKAO_PROV=$(PROV))"
	@GAOKAO_PROV=$(PROV) python3 skill/_shared/scripts/score_to_rank.py --score 580 --type 物理类 --year 2024 2>&1 | head -3 || true


.PHONY: status
status:
	@echo "=== 当前覆盖省份状态 ==="
	@for prov in hubei hunan jiangsu henan guangdong shandong hebei anhui; do \
		if [ -d skill/$$prov-zhiyuan ]; then \
			echo "  ✓ $$prov-zhiyuan"; \
		else \
			echo "  ⏳ $$prov-zhiyuan (未建)"; \
		fi; \
	done
