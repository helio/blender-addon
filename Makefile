# TAG reads git short SHA hash to be used as a version identifier
TAG?=$(shell git rev-parse --short=8 HEAD)

# Setting SHELL to bash allows bash commands to be executed by recipes.
# This is a requirement for 'setup-envtest.sh' in the test target.
# Options are set to exit when a recipe line exits non-zero or a piped command fails.
SHELL = /usr/bin/env bash -o pipefail
.SHELLFLAGS = -ec

# OS detection
UNAME_S := $(shell uname -s)

BLENDER_PATH?=/Applications/Blender.app/Contents/MacOS/Blender

##@ General

# The help target prints out all targets with their descriptions organized
# beneath their categories. The categories are represented by '##@' and the
# target descriptions by '##'. The awk commands is responsible for reading the
# entire set of makefiles included in this invocation, looking for lines of the
# file as xyz: ## something, and then pretty-format the target and help. Then,
# if there's a line with ##@ something, that gets pretty-printed as a category.
# More info on the usage of ANSI control characters for terminal formatting:
# https://en.wikipedia.org/wiki/ANSI_escape_code#SGR_parameters
# More info on the awk command:
# http://linuxcommand.org/lc3_adv_awk.php

help: ## Display this help.
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)


##@ Development

PWD=$(shell pwd)
USER_SCRIPTS_DIR=$(PWD)/user_scripts

.PHONY: run
run: ## Runs blender with addon
	mkdir -p $(USER_SCRIPTS_DIR)/addons
	ln -s $(PWD)/helio_blender_addon $(USER_SCRIPTS_DIR)/addons/
	BLENDER_USER_SCRIPTS=$(USER_SCRIPTS_DIR) /snap/bin/blender --addons helio_blender_addon
	rm -Rf $(USER_SCRIPTS_DIR)

release:
	rm helio-blender-addon-$(TAG).zip || true
	rm -Rf helio_blender_addon/__pycache__
	rm -Rf helio_blender_addon/*.pyc
	zip -r helio_blender_addon-$(TAG).zip helio_blender_addon/
