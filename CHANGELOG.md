# Changelog

## [1.2.0](https://github.com/canonical/hydra-operator/compare/v1.1.8...v1.2.0) (2025-07-09)


### Features

* add name to the create and update actions ([38f3b33](https://github.com/canonical/hydra-operator/commit/38f3b333b4f90a6209342308220e7451078ec636))
* expose client-uri via cli ([09e92b1](https://github.com/canonical/hydra-operator/commit/09e92b1e3ce5c4bd54c68fde06a421ec215f7475))
* expose contacts via cli ([8f007cc](https://github.com/canonical/hydra-operator/commit/8f007cc78d1a616590eeb28dd35798270ebdd504))


### Bug Fixes

* add serializer for metadata ([f10cf75](https://github.com/canonical/hydra-operator/commit/f10cf758b62ab5914cfb82e51349f5bb58c730d1))

## [1.1.8](https://github.com/canonical/hydra-operator/compare/v1.1.7...v1.1.8) (2025-07-08)


### Bug Fixes

* do not always set maintenance status ([de9678c](https://github.com/canonical/hydra-operator/commit/de9678c84b7c796340eb1be39ab96a79f030e061))
* don't restart service if config didn't change ([3d7f6b3](https://github.com/canonical/hydra-operator/commit/3d7f6b3de94a1473523e3f62ac4a110b1668dda1))
* use storedstate to check if config changed ([1e8d58e](https://github.com/canonical/hydra-operator/commit/1e8d58e779be990025d1034b7247e6f5f8ddab13))

## [1.1.7](https://github.com/canonical/hydra-operator/compare/v1.1.6...v1.1.7) (2025-07-04)


### Bug Fixes

* use proper charm name ([7044ff3](https://github.com/canonical/hydra-operator/commit/7044ff3dd6e23a4034fab806b11691c5b098d7b3))

## [1.1.6](https://github.com/canonical/hydra-operator/compare/v1.1.5...v1.1.6) (2025-07-02)


### Bug Fixes

* update to juju 0.20 and switch to use endpoints ([7bf6da8](https://github.com/canonical/hydra-operator/commit/7bf6da837b46486ebec50b25457ae69b1a253a23))
* update to use juju 0.20 ([107cb5b](https://github.com/canonical/hydra-operator/commit/107cb5bed828617b88d7783c9637eaf6e31c1764))

## [1.1.5](https://github.com/canonical/hydra-operator/compare/v1.1.4...v1.1.5) (2025-06-30)


### Bug Fixes

* add token hook integration ([8807ab4](https://github.com/canonical/hydra-operator/commit/8807ab42313781fe72d5e5e4ab602ed06e209a3c))
* block the charm when public ingress is not secured in non-dev mode ([d2df5c1](https://github.com/canonical/hydra-operator/commit/d2df5c1ec0dd358caa05238d0fb948c1f975a0ba))
* fix tests ([db5c0ff](https://github.com/canonical/hydra-operator/commit/db5c0ff0ca6db95789890f9a7dd51479fd8fb8a3))
* fix the issue that disregards the dev mode when dev config is set to true ([4a0ee32](https://github.com/canonical/hydra-operator/commit/4a0ee32026212bc229539dcc49e64455f59ce2d1))
* mark ui relation as mandatory ([b3b82bd](https://github.com/canonical/hydra-operator/commit/b3b82bd0d9c3bbca87294b60b864a06b2e1b81a8))

## [1.1.4](https://github.com/canonical/hydra-operator/compare/v1.1.3...v1.1.4) (2025-05-09)


### Bug Fixes

* fix constraint ([6a74fed](https://github.com/canonical/hydra-operator/commit/6a74fed3fb49e791d0270d762502d8f9c31267f6))

## [1.1.3](https://github.com/canonical/hydra-operator/compare/v1.1.2...v1.1.3) (2025-05-09)


### Bug Fixes

* add pod constraints ([f0b011c](https://github.com/canonical/hydra-operator/commit/f0b011c9243774a4c2baf9805e7fe0a727fd85a7))
* block charm if not integrated with ui ([f3726e4](https://github.com/canonical/hydra-operator/commit/f3726e44b4a47cb32bb8c09eb3b0f85d10ebe7d3))
* wait for login ui integration to be ready ([763c825](https://github.com/canonical/hydra-operator/commit/763c8254875d722731bb0d99e091d67b5ce3ac5b))

## [1.1.2](https://github.com/canonical/hydra-operator/compare/v1.1.1...v1.1.2) (2025-05-02)


### Bug Fixes

* fix tests ([0d6456f](https://github.com/canonical/hydra-operator/commit/0d6456f27a60eb36cdeb8c5d5674042917d0a6de))
* update charm dependent libs ([dd8d12f](https://github.com/canonical/hydra-operator/commit/dd8d12f6a647ad7faf6e9f7565e4f7b99b90f9e3))
* update charm libs ([85f17a0](https://github.com/canonical/hydra-operator/commit/85f17a0a93a1b80679e6afbfa23fe983999916b9))

## [1.1.1](https://github.com/canonical/hydra-operator/compare/v1.1.0...v1.1.1) (2025-04-01)


### Bug Fixes

* address CVEs ([6075941](https://github.com/canonical/hydra-operator/commit/6075941d6581ae42b9251ef44bf1097fc36960b7)), closes [#297](https://github.com/canonical/hydra-operator/issues/297)

## [1.1.0](https://github.com/canonical/hydra-operator/compare/v1.0.0...v1.1.0) (2025-03-24)


### Features

* add terraform module ([531ded2](https://github.com/canonical/hydra-operator/commit/531ded2679ca38bc3c18755feb21beb6d0003e59))
* add the terraform module for the charm ([d69a806](https://github.com/canonical/hydra-operator/commit/d69a80662ae069732c3198b06d91b8cd037d94af))


### Bug Fixes

* add reconcile-oauth-clients action ([0789efc](https://github.com/canonical/hydra-operator/commit/0789efc545516732c62c5ae4ae5f8ae685ba78b1))
* do not remove client on relation_broken ([4f16be0](https://github.com/canonical/hydra-operator/commit/4f16be0e45e61adcae5268b93a3473360aee468f)), closes [#268](https://github.com/canonical/hydra-operator/issues/268)
* fix the lint ([e0e34a9](https://github.com/canonical/hydra-operator/commit/e0e34a964565d1ee6441e50e457eed5d613c0b1b))
* fix the lint ci and traefik charm in integration test ([7f21c54](https://github.com/canonical/hydra-operator/commit/7f21c54e1c08e629ad438bec6a685f345c8b8c0b))
* provide optional flag in charmcraft.yaml ([358e91f](https://github.com/canonical/hydra-operator/commit/358e91f7cab8f8a033e217662d1abe0408854e08))

## 1.0.0 (2025-03-07)


### Features

* added alert rules to hydra ([58462ac](https://github.com/canonical/hydra-operator/commit/58462ac00457d10789ee834f4bb32edcd3aa618b))
* added automerge and auto-approve to charm lib updates ([53e4f18](https://github.com/canonical/hydra-operator/commit/53e4f18e83d5b98bfaff009ab4105b0545889606))
* added base-channel parameter to release-charm action ([d9c7e0a](https://github.com/canonical/hydra-operator/commit/d9c7e0afa7e0d9bd311bef019cf77bb5ecff5966))
* added grafana dashboard ([5fa646e](https://github.com/canonical/hydra-operator/commit/5fa646e5e4594dd257d7c62a12c3a0ae9646dd5d))
* added hydra side implementation of ui-endpoint-info interface ([#47](https://github.com/canonical/hydra-operator/issues/47)) ([d22b18e](https://github.com/canonical/hydra-operator/commit/d22b18e98d0a9a72a7af082a973a2ef9a4fb4980))
* added tracing integration to hydra operator ([0efe4d1](https://github.com/canonical/hydra-operator/commit/0efe4d1ec16a5b2c2ad26689176d0729c0bcf53e))
* added tracing unit test ([0efe4d1](https://github.com/canonical/hydra-operator/commit/0efe4d1ec16a5b2c2ad26689176d0729c0bcf53e))
* integrated with grafana-dashboard relation ([5fa646e](https://github.com/canonical/hydra-operator/commit/5fa646e5e4594dd257d7c62a12c3a0ae9646dd5d))
* introduce internal ingress ([92efe7a](https://github.com/canonical/hydra-operator/commit/92efe7ad001dda4b540f5422cea1a8516a4b2173))
* migrate to ingress v2 ([0987a59](https://github.com/canonical/hydra-operator/commit/0987a5978ebc36b1b1cf2d05339a449993007df8))
* updated hydra_endpoints relation name to hydra-endpoint-info ([2953db2](https://github.com/canonical/hydra-operator/commit/2953db263f8ac843f64281d01f413d7a71285220))
* updated login_ui_endpoints lib and associated unit test ([41b3c89](https://github.com/canonical/hydra-operator/commit/41b3c89685b6feb033709219a94cad4114bd868b))
* upgrade to v2 tracing ([45d5703](https://github.com/canonical/hydra-operator/commit/45d570380eb3d3f14031049443b0fb3766f840f0))
* use tracing v2 ([f2a0250](https://github.com/canonical/hydra-operator/commit/f2a0250d25fcc5d3c913e97e512555b9ed035703))


### Bug Fixes

* add back jsonschema wheel ([718f438](https://github.com/canonical/hydra-operator/commit/718f4380047d03acef2b5e7b979aea0be206a2d4))
* add config for device flow ([bfa65ee](https://github.com/canonical/hydra-operator/commit/bfa65ee5bab2e5551d449e0c121e1d3eb16cfc33))
* add config option for jwt at ([2bad3e0](https://github.com/canonical/hydra-operator/commit/2bad3e07b714e9697950c5531808c0fcaa8488fe))
* add device to allowed grants ([81a7924](https://github.com/canonical/hydra-operator/commit/81a7924e8398147c830319d94a5ac3ccd7ef3495))
* add jsonschema to PYDEPS ([fb8d92e](https://github.com/canonical/hydra-operator/commit/fb8d92e9a31b9e21bc45e851d396eb074747a32b))
* add jwt_access_token field to relation databag ([9b6f147](https://github.com/canonical/hydra-operator/commit/9b6f14705946e3fac1f1e89303967cd15fbf30fa))
* add name to prometheus scrape job ([870dc5e](https://github.com/canonical/hydra-operator/commit/870dc5e0f01e1e6c4177992a49b42e6995b54ff4))
* add ory logo ([ec6dbb2](https://github.com/canonical/hydra-operator/commit/ec6dbb250764639c55b00fa073facb131c55a50a))
* bumped microk8s version to 1.28-strict/stable in CI ([b8fa625](https://github.com/canonical/hydra-operator/commit/b8fa6254e61bd652090bf59856af643aa7b28f80))
* call super restore ([6851a72](https://github.com/canonical/hydra-operator/commit/6851a72b6f2b67a25735e3be7edbca3743b190d6))
* charmhub review fixes ([8309f0b](https://github.com/canonical/hydra-operator/commit/8309f0b1df4b1e76a61efb4a700f12dbd7039cf7))
* check if traefik is ready instead of checking if relation is created ([3ecfc52](https://github.com/canonical/hydra-operator/commit/3ecfc522b48fa2890abeb3d32c4c780adc7abb65))
* check sanity of args from db relation ([31210c0](https://github.com/canonical/hydra-operator/commit/31210c05aeac0512d359278cb892fad0564109e8))
* deal with db endpoints list ([9985eef](https://github.com/canonical/hydra-operator/commit/9985eefbbb164f2ea7f2bc56274b35b818e9e81b))
* drop jsonschema binary from charm build ([76e49ce](https://github.com/canonical/hydra-operator/commit/76e49ceca2c23936cb98a2d498ecf7624c302242))
* drop version check ([c8bd031](https://github.com/canonical/hydra-operator/commit/c8bd031488d3ed10b4ba1451b784be0bda4fbbd5))
* enable device flow for oauth lib ([aae9203](https://github.com/canonical/hydra-operator/commit/aae92039128175fcae3ddfd0e7ab3193f543e70d))
* expose app version to juju ([363e685](https://github.com/canonical/hydra-operator/commit/363e685feff3dac37aead000f0f05cceb3e47a62)), closes [#133](https://github.com/canonical/hydra-operator/issues/133)
* fix the internal ingress configuration ([a90baab](https://github.com/canonical/hydra-operator/commit/a90baaba04001b76a63b060985199b84224ab54a))
* fixed dashboard ([6f5332a](https://github.com/canonical/hydra-operator/commit/6f5332a62deec87b3c648e5127f43b6a3a025473))
* fixed dashboard description ([a558e19](https://github.com/canonical/hydra-operator/commit/a558e1937d952ab10c0fbcae85f0a1d853ddc54e))
* fixed grafana dashboard ([19dcee5](https://github.com/canonical/hydra-operator/commit/19dcee5f93014e4bdfdce40744817ee2fd7d4256))
* fixed issue with log file directory ([#75](https://github.com/canonical/hydra-operator/issues/75)) ([6312120](https://github.com/canonical/hydra-operator/commit/6312120308d15835e2cde6ad10b1a04bddf07af8))
* fixed issue with ui_login_relations ([a62c751](https://github.com/canonical/hydra-operator/commit/a62c7513dcbfafb1e990da6953fa714c0c1efc8b))
* fixed log alerts ([a8ccce1](https://github.com/canonical/hydra-operator/commit/a8ccce17b141f0f9fa047dc365a48d6682833049))
* fixed log queries in dashboard ([c8261d3](https://github.com/canonical/hydra-operator/commit/c8261d3beac673ce761d975d70d6e68fed591f62))
* fixed loki alert rule ([1c883f5](https://github.com/canonical/hydra-operator/commit/1c883f59b1af1cfef4eecaa28c74c80c7f1dbef4))
* fixed loki alert rule ([f4a39bf](https://github.com/canonical/hydra-operator/commit/f4a39bf584554942f328ea5d7009fa1761e1db01))
* go to WaitingStatus if ingress not ready ([2ef7bbc](https://github.com/canonical/hydra-operator/commit/2ef7bbc6de10ede855418d2e6204c9e78f64aedf)), closes [#145](https://github.com/canonical/hydra-operator/issues/145)
* handle database relation departed ([1c7305b](https://github.com/canonical/hydra-operator/commit/1c7305b746813a386b899de42e745e194b195946)), closes [#137](https://github.com/canonical/hydra-operator/issues/137)
* handle event being emitted multiple times ([e5b9bcf](https://github.com/canonical/hydra-operator/commit/e5b9bcf8ff538cf7a0d62eab76036121811f41f0))
* **loki-rule:** improve error handling in json parsing ([fc41e1c](https://github.com/canonical/hydra-operator/commit/fc41e1cfd26aebeb33792100dc866689b1093490))
* **loki-rule:** improve error handling in json parsing ([648d656](https://github.com/canonical/hydra-operator/commit/648d65693f9fd6ec52408008eaf7d457ca58f960))
* make "dev" flag configurable ([f9a0fd8](https://github.com/canonical/hydra-operator/commit/f9a0fd86914c84f4c06f56d57e194451e9a8ca6b)), closes [#130](https://github.com/canonical/hydra-operator/issues/130)
* make ingress relation mandatory ([80f3a3b](https://github.com/canonical/hydra-operator/commit/80f3a3bf71008df91eb7d58181492be65b6fc2ae))
* minor fixes in unit tests ([7f4acd5](https://github.com/canonical/hydra-operator/commit/7f4acd5bde764039cc7e810f5adf878188e76317))
* move to loki v1 for log forwarder ([64ebad4](https://github.com/canonical/hydra-operator/commit/64ebad48b75498ef06c6bf4bf5def62fab4b3b3c))
* move to use log forwarder across the board ([b2d7d25](https://github.com/canonical/hydra-operator/commit/b2d7d2574c4cbc5e03a15468207735c12ab577fb))
* patch if secret not found ([bba98a6](https://github.com/canonical/hydra-operator/commit/bba98a6c330316b7b44020fd9dd1f18788eae535))
* pined pytest-asyncio to version 0.21.1 ([0f3b8d0](https://github.com/canonical/hydra-operator/commit/0f3b8d0d93b8bcb71cd8b9ad2063a23cabeed632))
* rebased auto-approver.yaml ([86d7e0e](https://github.com/canonical/hydra-operator/commit/86d7e0e0bd4795f7dc01a196c6d91aea088cf756))
* refactored _hydra_layer property ([83361ae](https://github.com/canonical/hydra-operator/commit/83361aeaf67fccdaa8a18c96c34df4ef42550608))
* remove renovate workflow ([2290283](https://github.com/canonical/hydra-operator/commit/22902831be9fbda771da3faba9f9b2086d86607b))
* renamed release-approver to auto-approver ([cbb6e36](https://github.com/canonical/hydra-operator/commit/cbb6e3651d6c7585e8df8f9b2d425d91bb1fce3c))
* shorten hydra is_created and is_running methods ([3b4d8c7](https://github.com/canonical/hydra-operator/commit/3b4d8c7f5d580117f610ed38ca2247a5cf9dbf2f))
* status on migration action ([9daff4b](https://github.com/canonical/hydra-operator/commit/9daff4b6c43fc7e0e639c97f696944276d7391da))
* switch to use relation_broken on oauth_provider ([6b3d129](https://github.com/canonical/hydra-operator/commit/6b3d129f621ca281cbe85dd364b9453ddb8260cb))
* typo on is_running() ([24161f9](https://github.com/canonical/hydra-operator/commit/24161f9c965aca0178046f3c6b9cd725649486dd))
* update alert rules ([212393c](https://github.com/canonical/hydra-operator/commit/212393c2e34bcbe253a78cb0b09a2fce2108a8ef))
* update grafana dashboards ([01a2e6f](https://github.com/canonical/hydra-operator/commit/01a2e6f7d31fd1aeb225c80344a8b20ab3726729))
* update run-migration action ([3fe4232](https://github.com/canonical/hydra-operator/commit/3fe423209dc29836960197387fc29e81067e3473))
* update status message ([7f1187a](https://github.com/canonical/hydra-operator/commit/7f1187add832abe883601cbeeba677744ea65dd5))
* updated charm according to future change in tempo-k8s charm lib ([a0547f6](https://github.com/canonical/hydra-operator/commit/a0547f6fad4191747ad8180fa53d0d275b76a88b))
* updated charm.py according to changes in login_ui_endpoints relation ([c9f3f9a](https://github.com/canonical/hydra-operator/commit/c9f3f9aec83673f3ff80ec7eb6b4c8910804a926))
* updated checkout to v4 ([cbb6e36](https://github.com/canonical/hydra-operator/commit/cbb6e3651d6c7585e8df8f9b2d425d91bb1fce3c))
* updated login_ui_endpoints relation ([6c1dc16](https://github.com/canonical/hydra-operator/commit/6c1dc16bc7879cc67fd5d302ae1141a41fe638a0))
* updated to latest tempo lib ([7f4acd5](https://github.com/canonical/hydra-operator/commit/7f4acd5bde764039cc7e810f5adf878188e76317))
* use `oidc_error_url` ([90efa62](https://github.com/canonical/hydra-operator/commit/90efa62e02db63bc23fecf7cdcf8ba900e6fb4d2))
* use dataclasses.fields ([4a3b7d2](https://github.com/canonical/hydra-operator/commit/4a3b7d25f7558dbf926b05153a5e02b9deefcbfb))
* use DSN env var to run migration ([e004cf1](https://github.com/canonical/hydra-operator/commit/e004cf17435b8aef51be8fb23792f9be5a7c8cab))
* use http endpoint in endpoint-info integration ([061e5e9](https://github.com/canonical/hydra-operator/commit/061e5e97749c74e4f549461c44b451bc9566ef1d))
* use http endpoint in endpoint-info integration ([19c10d1](https://github.com/canonical/hydra-operator/commit/19c10d14e0c3ad45092e56d67362c1e764112012))
* use internal ingress if set, otherwise stick with k8s networking ([03bc551](https://github.com/canonical/hydra-operator/commit/03bc551e72fbe8f360c2c1a58f650d5d71990409))
* use oidc_error_url in config ([fafa239](https://github.com/canonical/hydra-operator/commit/fafa239d26ce0da057340e0aeae717d1e60f6499))
* use optional typing on get_provider_info ([996e8f2](https://github.com/canonical/hydra-operator/commit/996e8f253e896dbcbee3f3e0340bcb1cd75c4c03))
