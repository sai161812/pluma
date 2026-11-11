# Branch inventory before repository consolidation

Outcome: 23 remote and 24 local non-main branches removed after verified main
integration and bundle preservation. Only `main` remains locally/on GitHub.
The table below records original identities, not current branch existence.

2026-11-11. Every listed ref is preserved in the verified local recovery bundle.
Ancestor refs are included in the consolidated development history. Divergent refs are older/superseded lines retained in the bundle, not automatically merged.

| Ref | Commit | Disposition |
| --- | --- | --- |
| `refs/heads/archive/main-before-ui-sync-20261019-90aa05e` | `90aa05ebbc3518f2905bf73e91319ba25514832f` | divergent historical line; bundle retained |
| `refs/heads/docs/p11-main-handoff` | `26dc2799e758dc971e05315d8b97f2b376731240` | contained in development history |
| `refs/heads/integration/main-p00-p20-e99` | `0468a031238261bee5bc79bd04b16a3d1964a3a9` | contained in development history |
| `refs/heads/integration/verified-p00-p20-20261103` | `e6ceb6a2bf64817e9e81e9362e0a3e857769543a` | divergent historical line; bundle retained |
| `refs/heads/main` | `0468a031238261bee5bc79bd04b16a3d1964a3a9` | canonical branch |
| `refs/heads/p12-preparation` | `751fa87f589309f26afbfd5e2e495a40a3976dfa` | contained in development history |
| `refs/heads/recovery/main-before-p12-p20-20261103` | `26dc2799e758dc971e05315d8b97f2b376731240` | contained in development history |
| `refs/heads/recovery/p17-before-rollback-20261027-862b3fd` | `862b3fdb7bd964a25134082812d2700f112c5be9` | contained in development history |
| `refs/heads/recovery/pre-integration-20261103-67ad1c1` | `67ad1c1938f3f4653de61fdbf706b879025ea52e` | contained in development history |
| `refs/heads/recovery/pre-p20-repair-20261103-be8410d` | `be8410d6a8e3181d0e473004d39b3d5574621782` | contained in development history |
| `refs/heads/recovery/pre-p20-shell-fix-20261103-b4cfd49` | `b4cfd49c5db8ef7ec1db7be35d2c51e4dd861b13` | divergent historical line; bundle retained |
| `refs/heads/recovery/pre-p21-e100-20261103` | `0468a031238261bee5bc79bd04b16a3d1964a3a9` | contained in development history |
| `refs/heads/recovery/pre-p21-e101-20261103` | `d9f1fbcc96c871e199bc22306a0894c31675d2ce` | contained in development history |
| `refs/heads/recovery/pre-p21-e102-20261103` | `9936c116cfe99fb9e4ac936c1a0d4cbfcd747df9` | contained in development history |
| `refs/heads/recovery/pre-p21-e103-20261103` | `ef70aac78ad72b79ab66a92ca9cb0da05801aed3` | contained in development history |
| `refs/heads/recovery/pre-p22-e104-20261103` | `9d6653e3df6eb1ca7bd509590d58e401376a7262` | contained in development history |
| `refs/heads/recovery/pre-p22-e105-20261104` | `38825bcd9cee6e27fd29626f2a77d6702cfba044` | contained in development history |
| `refs/heads/recovery/pre-p23-e106-20261104` | `681c4398e115c7da35bec767baa71e70f43f6e6c` | contained in development history |
| `refs/heads/recovery/pre-p23-e107-20261104` | `3e4a03e0f8a261074e98ba9dc6f3baaacefba707` | contained in development history |
| `refs/heads/recovery/pre-p23-e108-20261104` | `3502e9ee7cd8a467e3d1e76e6915776ff7ade986` | contained in development history |
| `refs/heads/recovery/pre-remaining-work-20261110-c9f597f` | `c9f597f0f8ee4e0e0531fb724fff5105a5a3cfec` | contained in development history |
| `refs/heads/sai` | `23d9fcf864439d6dc5a4caa175c9931177f94bdd` | divergent historical line; bundle retained |
| `refs/heads/ui-polish` | `9150e81efe539e822b5a257ac2f2a23a24ee965e` | divergent historical line; bundle retained |
| `refs/heads/ui-polish-integration` | `9544752d1af4d675b50ff7aa8e99fb27da9c722f` | contained in development history |
| `refs/heads/ui-wiring` | `812a8b9c05e7c7e8852be1841ae5e47677f6382f` | contained in development history |
| `refs/remotes/origin/HEAD` | `0468a031238261bee5bc79bd04b16a3d1964a3a9` | contained in development history |
| `refs/remotes/origin/demo` | `91a51a92a5e0df4326bce8b6fd6bb1f33e7ce910` | divergent historical line; bundle retained |
| `refs/remotes/origin/docs/p11-main-handoff` | `c40433dc5e7fd62ac0b8697379d2dea058d6dbb0` | contained in development history |
| `refs/remotes/origin/integration/main-p00-p20-e99` | `0468a031238261bee5bc79bd04b16a3d1964a3a9` | contained in development history |
| `refs/remotes/origin/integration/verified-p00-p20-20261103` | `e6ceb6a2bf64817e9e81e9362e0a3e857769543a` | divergent historical line; bundle retained |
| `refs/remotes/origin/main` | `0468a031238261bee5bc79bd04b16a3d1964a3a9` | canonical branch |
| `refs/remotes/origin/p12-preparation` | `3fb26f70be6e8918e915212aa44d02d19cefdac1` | contained in development history |
| `refs/remotes/origin/recovery/main-before-p12-p20-20261103` | `26dc2799e758dc971e05315d8b97f2b376731240` | contained in development history |
| `refs/remotes/origin/recovery/p17-before-rollback-20261027-862b3fd` | `862b3fdb7bd964a25134082812d2700f112c5be9` | contained in development history |
| `refs/remotes/origin/recovery/pre-integration-20261103-67ad1c1` | `67ad1c1938f3f4653de61fdbf706b879025ea52e` | contained in development history |
| `refs/remotes/origin/recovery/pre-p20-repair-20261103-be8410d` | `be8410d6a8e3181d0e473004d39b3d5574621782` | contained in development history |
| `refs/remotes/origin/recovery/pre-p20-shell-fix-20261103-b4cfd49` | `b4cfd49c5db8ef7ec1db7be35d2c51e4dd861b13` | divergent historical line; bundle retained |
| `refs/remotes/origin/recovery/pre-p21-e100-20261103` | `0468a031238261bee5bc79bd04b16a3d1964a3a9` | contained in development history |
| `refs/remotes/origin/recovery/pre-p21-e101-20261103` | `d9f1fbcc96c871e199bc22306a0894c31675d2ce` | contained in development history |
| `refs/remotes/origin/recovery/pre-p21-e102-20261103` | `9936c116cfe99fb9e4ac936c1a0d4cbfcd747df9` | contained in development history |
| `refs/remotes/origin/recovery/pre-p21-e103-20261103` | `ef70aac78ad72b79ab66a92ca9cb0da05801aed3` | contained in development history |
| `refs/remotes/origin/recovery/pre-p22-e104-20261103` | `9d6653e3df6eb1ca7bd509590d58e401376a7262` | contained in development history |
| `refs/remotes/origin/recovery/pre-p22-e105-20261104` | `38825bcd9cee6e27fd29626f2a77d6702cfba044` | contained in development history |
| `refs/remotes/origin/recovery/pre-p23-e106-20261104` | `681c4398e115c7da35bec767baa71e70f43f6e6c` | contained in development history |
| `refs/remotes/origin/recovery/pre-p23-e107-20261104` | `3e4a03e0f8a261074e98ba9dc6f3baaacefba707` | contained in development history |
| `refs/remotes/origin/recovery/pre-p23-e108-20261104` | `3502e9ee7cd8a467e3d1e76e6915776ff7ade986` | contained in development history |
| `refs/remotes/origin/recovery/pre-remaining-work-20261110-c9f597f` | `c9f597f0f8ee4e0e0531fb724fff5105a5a3cfec` | contained in development history |
| `refs/remotes/origin/ui-polish` | `9150e81efe539e822b5a257ac2f2a23a24ee965e` | divergent historical line; bundle retained |
| `refs/remotes/origin/ui-polish-integration` | `9544752d1af4d675b50ff7aa8e99fb27da9c722f` | contained in development history |
| `refs/remotes/origin/ui-wiring` | `34a8471be6d159b245efe4e2f7fac1dd5c9d806f` | contained in development history |

Bundle: `output/repository-consolidation-20261111-01/all-refs-before-fetch.bundle`.
SHA-256: `4D429670B5DD59906C73DE8379D530F653AFD333908611FF962CA80848C03D08`.
The bundle also preserves existing tags, stash and tool recovery refs. No tags or stash are deleted by this consolidation.
