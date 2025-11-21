# Changelog

## 1.0.0 (2025-11-21)


### ⚠ BREAKING CHANGES

* drop public and admin ingresses, rewrite internal ingress to internal route

### Features

* add name to the create and update actions ([38f3b33](https://github.com/canonical/hydra-operator/commit/38f3b333b4f90a6209342308220e7451078ec636))
* add terraform module ([531ded2](https://github.com/canonical/hydra-operator/commit/531ded2679ca38bc3c18755feb21beb6d0003e59))
* add the terraform module for the charm ([d69a806](https://github.com/canonical/hydra-operator/commit/d69a80662ae069732c3198b06d91b8cd037d94af))
* expose client-uri via cli ([09e92b1](https://github.com/canonical/hydra-operator/commit/09e92b1e3ce5c4bd54c68fde06a421ec215f7475))
* expose contacts via cli ([8f007cc](https://github.com/canonical/hydra-operator/commit/8f007cc78d1a616590eeb28dd35798270ebdd504))
* introduce public-route relation ([1c1f1bc](https://github.com/canonical/hydra-operator/commit/1c1f1bc8b06857b2ba12bc5ce0baa63cfc6cf060))
* List all details except secrets in `list-oauth-clients` output ([e5fbd2a](https://github.com/canonical/hydra-operator/commit/e5fbd2a5127a844038657b6a53d04757709d0d28))
* List all details except secrets in `list-oauth-clients` output ([3b10539](https://github.com/canonical/hydra-operator/commit/3b105392f0338c044a34ac547c64eb75575e15c9))
* update juju_application resource name ([70a330f](https://github.com/canonical/hydra-operator/commit/70a330f6b877830bf1b993c80862e98dfb243f5b))
* upgrade to v2 tracing ([45d5703](https://github.com/canonical/hydra-operator/commit/45d570380eb3d3f14031049443b0fb3766f840f0))
* use tracing v2 ([f2a0250](https://github.com/canonical/hydra-operator/commit/f2a0250d25fcc5d3c913e97e512555b9ed035703))


### Bug Fixes

* add collect_status handler ([e76ba94](https://github.com/canonical/hydra-operator/commit/e76ba94956625ff15d8a6168d75b6cd87dfdbe9a))
* add config to prepopulate the hydra keys ([3a9a459](https://github.com/canonical/hydra-operator/commit/3a9a45976e2a8f15c712292a0a4814f881e265f8))
* add health check handlers ([ce8c745](https://github.com/canonical/hydra-operator/commit/ce8c7454d38821e4c456573c9c2df7188099f3c6))
* add pod constraints ([f0b011c](https://github.com/canonical/hydra-operator/commit/f0b011c9243774a4c2baf9805e7fe0a727fd85a7))
* add reconcile-oauth-clients action ([0789efc](https://github.com/canonical/hydra-operator/commit/0789efc545516732c62c5ae4ae5f8ae685ba78b1))
* add secret management actions ([0449395](https://github.com/canonical/hydra-operator/commit/0449395efd3b7f44a3e630f0c44e8c68fb800ad5))
* add serializer for metadata ([f10cf75](https://github.com/canonical/hydra-operator/commit/f10cf758b62ab5914cfb82e51349f5bb58c730d1))
* add token hook integration ([8807ab4](https://github.com/canonical/hydra-operator/commit/8807ab42313781fe72d5e5e4ab602ed06e209a3c))
* address CVEs ([6075941](https://github.com/canonical/hydra-operator/commit/6075941d6581ae42b9251ef44bf1097fc36960b7)), closes [#297](https://github.com/canonical/hydra-operator/issues/297)
* block charm if not integrated with ui ([f3726e4](https://github.com/canonical/hydra-operator/commit/f3726e44b4a47cb32bb8c09eb3b0f85d10ebe7d3))
* block the charm when public ingress is not secured in non-dev mode ([d2df5c1](https://github.com/canonical/hydra-operator/commit/d2df5c1ec0dd358caa05238d0fb948c1f975a0ba))
* do not always set maintenance status ([de9678c](https://github.com/canonical/hydra-operator/commit/de9678c84b7c796340eb1be39ab96a79f030e061))
* do not remove client on relation_broken ([4f16be0](https://github.com/canonical/hydra-operator/commit/4f16be0e45e61adcae5268b93a3473360aee468f)), closes [#268](https://github.com/canonical/hydra-operator/issues/268)
* don't restart service if config didn't change ([3d7f6b3](https://github.com/canonical/hydra-operator/commit/3d7f6b3de94a1473523e3f62ac4a110b1668dda1))
* drop public and admin ingresses, rewrite internal ingress to internal route ([d2b56d5](https://github.com/canonical/hydra-operator/commit/d2b56d52e0508b17100445797ec93e1a0268aa29))
* fix constraint ([6a74fed](https://github.com/canonical/hydra-operator/commit/6a74fed3fb49e791d0270d762502d8f9c31267f6))
* fix tests ([db5c0ff](https://github.com/canonical/hydra-operator/commit/db5c0ff0ca6db95789890f9a7dd51479fd8fb8a3))
* fix tests ([0d6456f](https://github.com/canonical/hydra-operator/commit/0d6456f27a60eb36cdeb8c5d5674042917d0a6de))
* fix the internal ingress configuration ([a90baab](https://github.com/canonical/hydra-operator/commit/a90baaba04001b76a63b060985199b84224ab54a))
* fix the issue that disregards the dev mode when dev config is set to true ([4a0ee32](https://github.com/canonical/hydra-operator/commit/4a0ee32026212bc229539dcc49e64455f59ce2d1))
* fix the lint ([e0e34a9](https://github.com/canonical/hydra-operator/commit/e0e34a964565d1ee6441e50e457eed5d613c0b1b))
* fix the lint ci and traefik charm in integration test ([7f21c54](https://github.com/canonical/hydra-operator/commit/7f21c54e1c08e629ad438bec6a685f345c8b8c0b))
* go to WaitingStatus if ingress not ready ([2ef7bbc](https://github.com/canonical/hydra-operator/commit/2ef7bbc6de10ede855418d2e6204c9e78f64aedf)), closes [#145](https://github.com/canonical/hydra-operator/issues/145)
* handle event being emitted multiple times ([e5b9bcf](https://github.com/canonical/hydra-operator/commit/e5b9bcf8ff538cf7a0d62eab76036121811f41f0))
* improve route integration handling logic ([28392b5](https://github.com/canonical/hydra-operator/commit/28392b5778bf380f911eadc66ffbdc7452489ef1))
* mark ui relation as mandatory ([b3b82bd](https://github.com/canonical/hydra-operator/commit/b3b82bd0d9c3bbca87294b60b864a06b2e1b81a8))
* move to loki v1 for log forwarder ([64ebad4](https://github.com/canonical/hydra-operator/commit/64ebad48b75498ef06c6bf4bf5def62fab4b3b3c))
* move to use log forwarder across the board ([b2d7d25](https://github.com/canonical/hydra-operator/commit/b2d7d2574c4cbc5e03a15468207735c12ab577fb))
* provide optional flag in charmcraft.yaml ([358e91f](https://github.com/canonical/hydra-operator/commit/358e91f7cab8f8a033e217662d1abe0408854e08))
* remove the storedstate to fix the missing config file issue when pod gets recreated ([2c492ce](https://github.com/canonical/hydra-operator/commit/2c492ceb9020ab9642037f411988602d2b549496))
* remove the storedstate to fix the missing config file issue when the pod gets recreated ([ba710b8](https://github.com/canonical/hydra-operator/commit/ba710b85751466055eb6012a7bde276dfc977364))
* stop service when database is gone ([8d3f400](https://github.com/canonical/hydra-operator/commit/8d3f400238857d79e6eb7d3221cf9c845a7a1738))
* switch to use -route relations in the tf module ([5856b84](https://github.com/canonical/hydra-operator/commit/5856b846f28df58a4a8d7153940629ab872ab1dc))
* update charm dependent libs ([81df22f](https://github.com/canonical/hydra-operator/commit/81df22f80796e26fa7cc292b78fe47fbaee6792a))
* update charm dependent libs ([dd8d12f](https://github.com/canonical/hydra-operator/commit/dd8d12f6a647ad7faf6e9f7565e4f7b99b90f9e3))
* update charm libs ([85f17a0](https://github.com/canonical/hydra-operator/commit/85f17a0a93a1b80679e6afbfa23fe983999916b9))
* update to juju 0.20 and switch to use endpoints ([7bf6da8](https://github.com/canonical/hydra-operator/commit/7bf6da837b46486ebec50b25457ae69b1a253a23))
* update to use juju 0.20 ([107cb5b](https://github.com/canonical/hydra-operator/commit/107cb5bed828617b88d7783c9637eaf6e31c1764))
* upgrade tf module to use 1.0.0 syntax ([9e1acf2](https://github.com/canonical/hydra-operator/commit/9e1acf26770d3f29fb865f702c0dc06c5da7c9f9))
* use `oidc_error_url` ([90efa62](https://github.com/canonical/hydra-operator/commit/90efa62e02db63bc23fecf7cdcf8ba900e6fb4d2))
* use oidc_error_url in config ([fafa239](https://github.com/canonical/hydra-operator/commit/fafa239d26ce0da057340e0aeae717d1e60f6499))
* use owner and name for model ds ([7c3a403](https://github.com/canonical/hydra-operator/commit/7c3a4036cbfa552242576ccd00a022aa84c24764))
* use proper charm name ([7044ff3](https://github.com/canonical/hydra-operator/commit/7044ff3dd6e23a4034fab806b11691c5b098d7b3))
* use proper intergration name for internal route ([68168de](https://github.com/canonical/hydra-operator/commit/68168de505c97fe9049b6a8bba3b2d7dda7cc78f))
* use storedstate to check if config changed ([1e8d58e](https://github.com/canonical/hydra-operator/commit/1e8d58e779be990025d1034b7247e6f5f8ddab13))
* use terraform module in deployment ([31ed04a](https://github.com/canonical/hydra-operator/commit/31ed04a0059b5c4862f3ce233daa2b999456e502))
* wait for login ui integration to be ready ([763c825](https://github.com/canonical/hydra-operator/commit/763c8254875d722731bb0d99e091d67b5ce3ac5b))
