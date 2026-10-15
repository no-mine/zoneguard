SHELL       := /bin/bash

NAME        := zoneguard
VERSION     := $(shell grep -m1 '^version' pyproject.toml | sed -E 's/.*"([^"]+)".*/\1/')
TARBALL     := $(NAME)-$(VERSION).tar.gz

SDIST_DIR   := $(CURDIR)/dist/sdist
RPM_TOPDIR  := $(CURDIR)/dist/rpmbuild
DEB_OUT_DIR := $(CURDIR)/dist/deb

CONTAINER_DIR := packaging/containers
FEDORA_IMAGE  := $(NAME)-build-fedora
ROCKY9_IMAGE  := $(NAME)-build-rocky9
UBUNTU_IMAGE  := $(NAME)-build-ubuntu
DEBIAN_IMAGE  := $(NAME)-build-debian

PODMAN      := podman

# Everything that goes into the source tarball every package build unpacks.
SOURCE_FILES := pyproject.toml README.md CHANGELOG.md src data tests packaging

.PHONY: all packages rpm rpm-fedora rpm-rocky9 deb deb-ubuntu deb-debian \
        image-fedora image-rocky9 image-ubuntu image-debian images \
        shell-fedora shell-rocky9 shell-ubuntu shell-debian \
        sdist clean clean-images

all: packages

## Build everything: RPMs and .debs for every supported target.
packages: rpm deb

## Build RPMs for every supported target.
rpm: rpm-fedora rpm-rocky9

## Build .debs for every supported target.
deb: deb-ubuntu deb-debian

## --- container images -------------------------------------------------

image-fedora:
	$(PODMAN) build -t $(FEDORA_IMAGE) -f $(CONTAINER_DIR)/Containerfile.fedora $(CONTAINER_DIR)

image-rocky9:
	$(PODMAN) build -t $(ROCKY9_IMAGE) -f $(CONTAINER_DIR)/Containerfile.rocky9 $(CONTAINER_DIR)

image-ubuntu:
	$(PODMAN) build -t $(UBUNTU_IMAGE) -f $(CONTAINER_DIR)/Containerfile.ubuntu $(CONTAINER_DIR)

image-debian:
	$(PODMAN) build -t $(DEBIAN_IMAGE) -f $(CONTAINER_DIR)/Containerfile.debian $(CONTAINER_DIR)

images: image-fedora image-rocky9 image-ubuntu image-debian

## --- source tarball -----------------------------------------------------
# Shared by every package target so the spec/control files stay the single
# source of truth for build deps, not this step.

$(SDIST_DIR)/$(TARBALL): $(SOURCE_FILES)
	mkdir -p $(SDIST_DIR)
	tar --exclude-vcs \
	    --exclude='./dist' \
	    --exclude='./.venv' \
	    --exclude='__pycache__' \
	    --exclude='*.egg-info' \
	    --transform 's,^\.,$(NAME)-$(VERSION),' \
	    -czf $@ $(addprefix ./,$(SOURCE_FILES))

sdist: $(SDIST_DIR)/$(TARBALL)

## --- rpm builds ---------------------------------------------------------
# Build deps are resolved from the spec file itself via dnf builddep, so
# the containers only carry generic RPM tooling.

rpm-fedora: image-fedora $(SDIST_DIR)/$(TARBALL)
	mkdir -p $(RPM_TOPDIR)/{SPECS,BUILD,BUILDROOT,RPMS,SRPMS}
	$(PODMAN) run --rm -v $(CURDIR):/src:Z -w /src $(FEDORA_IMAGE) \
		bash -c "dnf builddep -y packaging/$(NAME).spec && \
			rpmbuild --define '_topdir /src/dist/rpmbuild' --define '_sourcedir /src/dist/sdist' \
				-ba packaging/$(NAME).spec"
	@echo "Fedora packages in $(RPM_TOPDIR)/RPMS and $(RPM_TOPDIR)/SRPMS"

rpm-rocky9: image-rocky9 $(SDIST_DIR)/$(TARBALL)
	mkdir -p $(RPM_TOPDIR)/{SPECS,BUILD,BUILDROOT,RPMS,SRPMS}
	$(PODMAN) run --rm -v $(CURDIR):/src:Z -w /src $(ROCKY9_IMAGE) \
		bash -c "dnf builddep -y packaging/$(NAME).spec && \
			rpmbuild --define '_topdir /src/dist/rpmbuild' --define '_sourcedir /src/dist/sdist' \
				-ba packaging/$(NAME).spec"
	@echo "Rocky 9 packages in $(RPM_TOPDIR)/RPMS and $(RPM_TOPDIR)/SRPMS"

## --- deb builds -----------------------------------------------------------
# dpkg-buildpackage writes output as *siblings* of the source directory, so
# the build happens in the container's own /build (not the bind mount) and
# the resulting .deb/.changes/.buildinfo get copied back out afterward.
# Build deps come from debian/control via mk-build-deps, mirroring the RPM
# approach -- the containers only carry generic .deb build tooling.

deb-ubuntu: image-ubuntu $(SDIST_DIR)/$(TARBALL)
	mkdir -p $(DEB_OUT_DIR)
	$(PODMAN) run --rm -v $(CURDIR):/src:Z $(UBUNTU_IMAGE) bash -c " \
		set -e && \
		rm -rf /build/$(NAME)-$(VERSION) && \
		tar -xzf /src/dist/sdist/$(TARBALL) -C /build && \
		cp -r /src/packaging/debian /build/$(NAME)-$(VERSION)/debian && \
		cd /build/$(NAME)-$(VERSION) && \
		mk-build-deps --install --remove --tool='apt-get -y --no-install-recommends' debian/control && \
		dpkg-buildpackage -us -uc -b && \
		mkdir -p /src/dist/deb && \
		cp /build/*.deb /build/*.changes /build/*.buildinfo /src/dist/deb/ 2>/dev/null || true \
	"
	@echo "Ubuntu packages in $(DEB_OUT_DIR)"

deb-debian: image-debian $(SDIST_DIR)/$(TARBALL)
	mkdir -p $(DEB_OUT_DIR)
	$(PODMAN) run --rm -v $(CURDIR):/src:Z $(DEBIAN_IMAGE) bash -c " \
		set -e && \
		rm -rf /build/$(NAME)-$(VERSION) && \
		tar -xzf /src/dist/sdist/$(TARBALL) -C /build && \
		cp -r /src/packaging/debian /build/$(NAME)-$(VERSION)/debian && \
		cd /build/$(NAME)-$(VERSION) && \
		mk-build-deps --install --remove --tool='apt-get -y --no-install-recommends' debian/control && \
		dpkg-buildpackage -us -uc -b && \
		mkdir -p /src/dist/deb && \
		cp /build/*.deb /build/*.changes /build/*.buildinfo /src/dist/deb/ 2>/dev/null || true \
	"
	@echo "Debian packages in $(DEB_OUT_DIR)"

## --- debugging ------------------------------------------------------------

shell-fedora: image-fedora
	$(PODMAN) run --rm -it -v $(CURDIR):/src:Z -w /src $(FEDORA_IMAGE) bash

shell-rocky9: image-rocky9
	$(PODMAN) run --rm -it -v $(CURDIR):/src:Z -w /src $(ROCKY9_IMAGE) bash

shell-ubuntu: image-ubuntu
	$(PODMAN) run --rm -it -v $(CURDIR):/src:Z -w /src $(UBUNTU_IMAGE) bash

shell-debian: image-debian
	$(PODMAN) run --rm -it -v $(CURDIR):/src:Z -w /src $(DEBIAN_IMAGE) bash

## --- cleanup ----------------------------------------------------------

clean:
	rm -rf dist

clean-images:
	-$(PODMAN) rmi $(FEDORA_IMAGE) $(ROCKY9_IMAGE) $(UBUNTU_IMAGE) $(DEBIAN_IMAGE)
