# Base Sepolia run 20261017T141639Z (verified)

The carbon-aware HourProof demo, run once on **Base Sepolia (chain 84532)** on 17 Oct 2026 with real UltraHonk proofs and real ML-DSA-44 signatures. 80 transactions, 114,132,609 gas, all 8 attacks refused, status `done`.

## How it was verified (read-only, no key needed)

```bash
python -m hourproof verify --state evidence/base-sepolia-20261017T141639Z/state.json   # -> verify.txt
python3 scripts/check_public_run.py evidence/base-sepolia-20261017T141639Z/state.json   # -> independent-checks.txt
make verify-evidence    # both
```

- `verify.txt`: all 80 receipts succeeded and match; 15/15 contracts have code; ClaimManager points at the deployed verifiers and intensity oracle; both verifiers are the real 18,145-byte UltraHonk contracts; the exact proof bytes from both submit transactions re-verify on-chain against the public inputs ClaimManager rebuilds (170 and 339), and fail with one flipped byte; proven coverage ≥ 75.00 % and residual ≤ 546.1 t; 7/7 plans revealed.
- `independent-checks.txt` (cast only, no project code): the note settled after its deadline with `SettledResidual(kpiMet=false, 546,125 kg, 600 bps)` against the 428,509 kg target fixed at deployment, investor paid 60 tUSD; 7 issuer-A batches accepted (`BatchIssued` nonces 0–6); registry B kept only its one legitimate batch; the refused attacks changed nothing on-chain; every wallet's nonce equals the transactions recorded across all three public attempts, none pending.

## What is on-chain and what is not

- On-chain: every transaction below, the two ZK proofs (in the submit transactions' calldata), the ML-DSA signatures (in the issuance calldata), the settlement, the reveals.
- Refused **before broadcast** (gas estimation hit the contract's custom error, so no transaction exists): `SliceAlreadyClaimed`, `ExceedsProduction`, `BadIssuerSignature`, `ProofRejected` ×2, `AlreadyPosted`. Their absence of effect is checked on-chain (state unchanged, ghost wallet nonce 0).
- Refused **by the prover, locally**: a coverage 1 bp above the truth and a residual 1 kg below it (no witness exists).
- The private hourly load never left the machine; only its Pedersen commitment is on-chain.

## Contracts

| Contract | Address |
|---|---|
| ProductionOracle | [0x15f4b02e608aCfba63b78A13858DcFa4f08EB4C9](https://sepolia.basescan.org/address/0x15f4b02e608aCfba63b78A13858DcFa4f08EB4C9) |
| SliceLedger | [0xe4E4eE03095d59E5562FF7C738FC95628aC381Aa](https://sepolia.basescan.org/address/0xe4E4eE03095d59E5562FF7C738FC95628aC381Aa) |
| MLDSA_F1600Helper | [0x639390D976b9fB51f5F776f6755e9eaFF0aed5cf](https://sepolia.basescan.org/address/0x639390D976b9fB51f5F776f6755e9eaFF0aed5cf) |
| MLDSA44Verifier | [0x7838De632e0f2be3a1a2136efF3D0f1b2F0dD5af](https://sepolia.basescan.org/address/0x7838De632e0f2be3a1a2136efF3D0f1b2F0dD5af) |
| IssuerA_PQKey | [0x3643b8560403Ab14Aa340554A677c97Ec5F1d62f](https://sepolia.basescan.org/address/0x3643b8560403Ab14Aa340554A677c97Ec5F1d62f) |
| IssuerB_PQKey | [0x4c2beDE3378EdFF18f742Bef4F61A373282c1085](https://sepolia.basescan.org/address/0x4c2beDE3378EdFF18f742Bef4F61A373282c1085) |
| RegistryA | [0xD5fbcd92f1e0f861d4f0e98C7315362ba5602494](https://sepolia.basescan.org/address/0xD5fbcd92f1e0f861d4f0e98C7315362ba5602494) |
| RegistryB | [0x3743199301c8d78b0f163715Ac33caBC06E5e5D8](https://sepolia.basescan.org/address/0x3743199301c8d78b0f163715Ac33caBC06E5e5D8) |
| HonkVerifier | [0x4a2FE5e531e758F9ab5606Ea9bB6389b300d8D7F](https://sepolia.basescan.org/address/0x4a2FE5e531e758F9ab5606Ea9bB6389b300d8D7F) |
| ClaimManager | [0x54537970a7f67621476FbcF8564C85c04Ef8d280](https://sepolia.basescan.org/address/0x54537970a7f67621476FbcF8564C85c04Ef8d280) |
| IntensityOracle | [0xF99Effe54c22b1A030E3357859dC400630aA0227](https://sepolia.basescan.org/address/0xF99Effe54c22b1A030E3357859dC400630aA0227) |
| EmissionsHonkVerifier | [0xB2F388B518b677D1310ed894762ED86BcED080FD](https://sepolia.basescan.org/address/0xB2F388B518b677D1310ed894762ED86BcED080FD) |
| AgentCommitLog | [0xF195BB239AB18101461FA21cb4e0525BD1B89748](https://sepolia.basescan.org/address/0xF195BB239AB18101461FA21cb4e0525BD1B89748) |
| TestUSD | [0x5FdF47AAD20CC310672A9cDc2633AfC02f844CA1](https://sepolia.basescan.org/address/0x5FdF47AAD20CC310672A9cDc2633AfC02f844CA1) |
| SustainabilityLinkedNote | [0xc084E6cE004966E243a745d7b0adf108BD6B38b4](https://sepolia.basescan.org/address/0xc084E6cE004966E243a745d7b0adf108BD6B38b4) |

## Transactions

| Step | Transaction | Sender | Block | Gas |
|---|---|---|---:|---:|
| preflight | [fund issuer_ops](https://sepolia.basescan.org/tx/0xd507cbd9535132300b3f61c0857bcf2cf88b85d0eb62dd1b2253be1c341e17b5) | admin | 48239165 | 21,000 |
| preflight | [fund buyer](https://sepolia.basescan.org/tx/0x9247414aa6a48130d5e3b59108844f13646aa8874e779c5222517b8f1ab96e70) | admin | 48239169 | 21,000 |
| preflight | [fund agent](https://sepolia.basescan.org/tx/0x0f3872e4e8b5e14a4d96446941c591a728f2d35cbe1e74a64111a84ab694ca08) | admin | 48239172 | 21,000 |
| deploy | [deploy ProductionOracle](https://sepolia.basescan.org/tx/0xddb1762d7baf961f4aa0e6db57edeba72c17a35cf0c4e5b6e02d09051a7a65fd) | admin | 48239179 | 437,963 |
| deploy | [deploy SliceLedger](https://sepolia.basescan.org/tx/0x9b71220b0467fa9d3aa930ab1f10b7f1f941d4f7813c45fcc933673d445a554e) | admin | 48239182 | 388,657 |
| deploy | [deploy ML-DSA Keccak helper](https://sepolia.basescan.org/tx/0xa147cb48cce9e9c9c75423ed46de34877270995c181e22ea2f95298fd228aa0a) | admin | 48239185 | 4,716,316 |
| deploy | [deploy MLDSA44Verifier](https://sepolia.basescan.org/tx/0xad57266a625c1e1f4407c56fdf2994b4e56fed543bcac2698fa39c3f346f7abf) | admin | 48239189 | 5,175,028 |
| deploy | [deploy issuer A ML-DSA public key](https://sepolia.basescan.org/tx/0xf1963214117ac3b8edac2af317fab7f6d0c36651fbc3dd07ecf5bc11ac890fc6) | admin | 48239192 | 4,434,687 |
| deploy | [deploy issuer B ML-DSA public key](https://sepolia.basescan.org/tx/0xfc8e1b43ef871c27286ba205cbec2f083032cda9b7ce1edc420899feef304079) | admin | 48239195 | 4,434,387 |
| deploy | [deploy CertRegistry](https://sepolia.basescan.org/tx/0x73a6a090e8510bfae864d9261022ef59ac06b9beb04d763205522b3c1a1c05f3) | admin | 48239198 | 1,422,255 |
| deploy | [deploy CertRegistry](https://sepolia.basescan.org/tx/0x9b962833f3969ee34d7779eafae1970399cf7925cb9cd6a6471042701a5bfb6e) | admin | 48239201 | 1,422,255 |
| deploy | [deploy library RelationsLib](https://sepolia.basescan.org/tx/0x79a394a16babf7620b017f7609ebcca31a8bc0387981a1a49cbfbf1e11e272b5) | admin | 48239204 | 1,775,759 |
| deploy | [deploy library ZKTranscriptLib](https://sepolia.basescan.org/tx/0x8435696815a971cdeb6420085c27fcfa6b9c1ee219c15cf4418195b2d7de1e2e) | admin | 48239207 | 1,383,456 |
| deploy | [deploy UltraHonk verifier](https://sepolia.basescan.org/tx/0x825b5ecd4e528e91e29b452b845b8dd774d65d6577807237c26e5eb66bb6d8b1) | admin | 48239211 | 3,975,276 |
| deploy | [deploy ClaimManager](https://sepolia.basescan.org/tx/0xbccef26536a704a68e76b9f93b65810d2478ce4250574232a37c8967dba476c6) | admin | 48239214 | 1,809,981 |
| deploy | [deploy IntensityOracle](https://sepolia.basescan.org/tx/0x4c9cab36457814383c023853b5588e39dbb69dc43a8938d5b8739be2b4e20ace) | admin | 48239217 | 526,918 |
| deploy | [deploy library EmissionsRelationsLib](https://sepolia.basescan.org/tx/0x9ba74a8bdba3fe369bd34407f2f13a974eef9fce824fedffa0eadebfe0e249fc) | admin | 48239221 | 1,775,759 |
| deploy | [deploy library EmissionsZKTranscriptLib](https://sepolia.basescan.org/tx/0x3c3239e155f38350d292afa3527cfca0241ea6fd1632184973f37b6a82b6f5c6) | admin | 48239225 | 1,383,456 |
| deploy | [deploy UltraHonk emissions verifier](https://sepolia.basescan.org/tx/0x25836be999aa2140748fd2c40ba3ba3e7038ab30b0bd112c006938784ff8fcd8) | admin | 48239228 | 3,975,328 |
| deploy | [deploy AgentCommitLog](https://sepolia.basescan.org/tx/0xa8e5cc454dbcc6c38b9d8a8f6e31772ad034f9e18868b4b5fab1943aa73ec6a2) | admin | 48239232 | 316,467 |
| deploy | [deploy TestUSD](https://sepolia.basescan.org/tx/0xcbed50ec3d7857f4f160fead4d564801d12d4aba32bb590e5c9a2fdc542f72c2) | admin | 48239236 | 408,204 |
| deploy | [deploy SustainabilityLinkedNote](https://sepolia.basescan.org/tx/0x0303c8f7ea57c54c0701dff2eea93c7048cad632bb1c1d6a5b861fd6d8362eaf) | admin | 48239240 | 889,094 |
| deploy | [setPoster](https://sepolia.basescan.org/tx/0xa545762b49efad66a510350cc2e106c3d3a10643677d10317eb6a7db0f649e95) | admin | 48239243 | 45,638 |
| deploy | [setRegistry](https://sepolia.basescan.org/tx/0x10dbed38f1abe464c5c26c8320bd8986a9aecec4b0acd4409baccdea5a4dfead) | admin | 48239246 | 45,639 |
| deploy | [setRegistry](https://sepolia.basescan.org/tx/0xdc01f43664ea150c715e963e1b9c48093d27f24d9eb2b53236be6d8804ddbe8e) | admin | 48239249 | 45,734 |
| deploy | [setClaimSink](https://sepolia.basescan.org/tx/0x0a57514cb807b0ddd4b425a4004b4fbd9fd28e7adae956ff112c364b22e30867) | admin | 48239252 | 43,790 |
| deploy | [setRegistry](https://sepolia.basescan.org/tx/0xb477c75621eceaa9fd9e43a068aa651fb5511d4368536ea311adc84386543fbb) | admin | 48239255 | 45,639 |
| deploy | [setRegistry](https://sepolia.basescan.org/tx/0x5e3a98a5c907302926762a85e3930efdcc6f68f72b90240020e32c6fb9854432) | admin | 48239258 | 45,734 |
| deploy | [setClaimSink](https://sepolia.basescan.org/tx/0x2be02e77dda4cfc60fb30ae9b1d806675effc44e794fb4aa834afac9ea903c18) | admin | 48239262 | 43,790 |
| deploy | [registerIssuer](https://sepolia.basescan.org/tx/0xc5dfc344128d689054171217fa60eb3308d919d14ff12ae6bfd55b6eba05cb23) | admin | 48239267 | 46,153 |
| deploy | [registerIssuer](https://sepolia.basescan.org/tx/0x2d7cd7f6063ee31fc8bdc52d5b1385a489e7cf41557ea78f9b6b3da82de0fed9) | admin | 48239272 | 46,153 |
| deploy | [setDataHub](https://sepolia.basescan.org/tx/0x3abce6b376290fab0823f746662b6b44d884d118164d426b0a398cdc083a38f9) | admin | 48239275 | 45,765 |
| deploy | [setOracle](https://sepolia.basescan.org/tx/0x8d059af45af3a67c550fbe32842f0f25a61281b267e1e159ac7daf9e47ca9c53) | admin | 48239278 | 45,705 |
| deploy | [setEmissionsVerifier](https://sepolia.basescan.org/tx/0x81fb1993ffdc14eb2719e0269fb8d3cd99dfb9f54c4160235232b76ebf8c064a) | admin | 48239298 | 45,111 |
| deploy | [setIntensityOracle](https://sepolia.basescan.org/tx/0x7a15f928fac8351185b05c2aab1b21be3c29a3f7fc7dec2a5366ebfaa73c08ae) | admin | 48239301 | 67,659 |
| agent_commit | [commit plan 2025-11-10](https://sepolia.basescan.org/tx/0xd9db4e3b2d6b4b4afea023db1c8f044b7f4cfca43ff2e604dba8264c604768ec) | agent | 48239304 | 69,995 |
| agent_commit | [commit plan 2025-11-11](https://sepolia.basescan.org/tx/0x85dfc6e620c5946d5236a49af3feec1a463219c504f6fd56cdbbd3f1e29a3b2c) | agent | 48239307 | 70,007 |
| agent_commit | [commit plan 2025-11-12](https://sepolia.basescan.org/tx/0x32cd75bf21eca0e5d0031cea5cf359239d837ca4cdfc26e9aa07dcdbd69330d8) | agent | 48239311 | 69,995 |
| agent_commit | [commit plan 2025-11-13](https://sepolia.basescan.org/tx/0x1974604bcc8e421600d5813e9872a87355ac892bb3b545bb4535854a732f6bdf) | agent | 48239315 | 70,007 |
| agent_commit | [commit plan 2025-11-14](https://sepolia.basescan.org/tx/0x7546437acc7a5623629937301bb542fec3361a5bf665252c331911970a2b1ed9) | agent | 48239319 | 69,995 |
| agent_commit | [commit plan 2025-11-15](https://sepolia.basescan.org/tx/0x6c042f70f2586679d7387a868a9a8b082e96433418b4d0759cf10295b5d8580a) | agent | 48239323 | 70,007 |
| agent_commit | [commit plan 2025-11-16](https://sepolia.basescan.org/tx/0x3043bbd2d4c0ca6df386624edff269841908b711b139d1337d3bb40118f99953) | agent | 48239327 | 69,995 |
| oracle | [post DK-wind-declared hours 0-83](https://sepolia.basescan.org/tx/0x1a71d43df7726ce12095676ad73c8f0fd1bbe940e76b650c0b6ddba0563ce2ef) | oracle | 48239331 | 4,109,391 |
| oracle | [post DK-wind-declared hours 84-167](https://sepolia.basescan.org/tx/0x6e1e61bae13d55f898c7cf57ee257a3388cab965ab382a917f0080e340b9ca64) | oracle | 48239334 | 4,109,355 |
| oracle | [post DK-other-clean-declared hours 0-83](https://sepolia.basescan.org/tx/0x4edf0d2978fb2d933450fa2317983e4d062335e807c8faca2066f42489e8a5f8) | oracle | 48239337 | 4,108,683 |
| oracle | [post DK-other-clean-declared hours 84-167](https://sepolia.basescan.org/tx/0xf049116e8e61ba1a96fcf82fcc936687e2dc4e54e653a19e77c231baecd4207c) | oracle | 48239340 | 4,108,719 |
| intensity | [post intensity hours 0-83](https://sepolia.basescan.org/tx/0x36312d68ef528ad607646bde15e509b20e773f8b5c74a47b1f98264a730d409f) | oracle | 48239343 | 2,166,240 |
| intensity | [post intensity hours 84-167](https://sepolia.basescan.org/tx/0x105be4f628494b14bea7df87d686cd9957cea7c9f1a1290f535c15c8e3af1c48) | oracle | 48239346 | 2,166,240 |
| issue | [issue day 1 (24 certs)](https://sepolia.basescan.org/tx/0x997fa5b03e714a242d4b26b065cdaea6a00fe5d909846f5e2fb121662825897d) | issuer_ops | 48239351 | 3,230,373 |
| issue | [issue day 2 (24 certs)](https://sepolia.basescan.org/tx/0xa487f90882b31c3942779a3078b66e2103cdb4640497ef09b687c0200f35e712) | issuer_ops | 48239357 | 3,228,626 |
| issue | [issue day 3 (24 certs)](https://sepolia.basescan.org/tx/0x85111633aa89724bf77e5673d519faa9c5e2ed1146ed3d632c7a540c2bf91627) | issuer_ops | 48239361 | 3,231,051 |
| issue | [issue day 4 (24 certs)](https://sepolia.basescan.org/tx/0x9b2852f32f06810f31e1088904abc8a69bc67a629d47af9f10d6dcf98ae973e0) | issuer_ops | 48239365 | 3,228,788 |
| issue | [issue day 5 (24 certs)](https://sepolia.basescan.org/tx/0x2c1a2be4f46009115dc54d86845fad0587fc5a9cd0536fcc5fcdb904cb4ad5bb) | issuer_ops | 48239370 | 3,232,138 |
| issue | [issue day 6 (24 certs)](https://sepolia.basescan.org/tx/0x7c467888891b487b108a1de16e69888712dbf87480ea9298c6a3ab1bea7d3e3a) | issuer_ops | 48239375 | 3,229,346 |
| issue | [issue day 7 (24 certs)](https://sepolia.basescan.org/tx/0x57070bdf92bd384f16392b39fbee016d42c0a3b2c050a36c72b58de115e450f2) | issuer_ops | 48239379 | 3,229,790 |
| claim | [openClaim](https://sepolia.basescan.org/tx/0xe596475b32c5ee013bee5f554c1a5759288094627e38b2ab0b55c0ab8df93a16) | buyer | 48239387 | 53,450 |
| claim | [cancel certificates 1-40](https://sepolia.basescan.org/tx/0xc14b25d98ba06f40a6f9c0b83e8c3045254ecd9ee01381346511d8d92c836b00) | buyer | 48239391 | 3,597,195 |
| claim | [cancel certificates 41-80](https://sepolia.basescan.org/tx/0xdbab939dce0435ce33d82857126a975784130abc1055b6f303f9f592053b2e04) | buyer | 48239395 | 4,237,380 |
| claim | [cancel certificates 81-120](https://sepolia.basescan.org/tx/0x8fd5d27a8971d24d7b4bb7fec273610fbfbb0dbfa8873d0954ea4de6ecedce0e) | buyer | 48239400 | 3,920,070 |
| claim | [cancel certificates 121-160](https://sepolia.basescan.org/tx/0xd5aa193842f440aa2592054c16afde6a2135f4343079698e94294ae201842182) | buyer | 48239404 | 3,625,425 |
| claim | [cancel certificates 161-168](https://sepolia.basescan.org/tx/0x64913d050cb77393cfc0b7df12fc6000ba38ce6fc3efa9b336ba9d2af56127ad) | buyer | 48239407 | 884,149 |
| attacks_supply | [registry B issues the SAME MWh (legitimately signed)](https://sepolia.basescan.org/tx/0xd7b0d436c965a8a9eecbf61c3de41860d0080fdcccc049096e2dae9e580b0fef) | issuer_ops | 48239412 | 1,423,887 |
| attest | [attestLoad](https://sepolia.basescan.org/tx/0x492b858c97c7e2e3f523c26ba792269389ee7002700c73f02b2a287811d46a37) | datahub | 48239421 | 49,397 |
| prove | [submit coverage proof](https://sepolia.basescan.org/tx/0x354390f9b8422f976f1995215c275cdf33cb58910685513008ed8c9e19729d5e) | buyer | 48239426 | 4,541,012 |
| prove_emissions | [submit emissions proof](https://sepolia.basescan.org/tx/0x8712cbd4a5de4e57fa747525afd2e78451eeb05ad77be3098077271be2146c36) | buyer | 48239433 | 5,387,099 |
| note | [mint test USD to investor](https://sepolia.basescan.org/tx/0x20aa01b8f92f518e66627b62b8324c16ce2834ec9b99b9d8f0ccb38c724c50cb) | admin | 48239441 | 68,353 |
| note | [mint test USD to issuer](https://sepolia.basescan.org/tx/0xd4708b2576008ed86b2e340fa8cf4406d0acb9256bb19cff28c07832c1c868e7) | admin | 48239445 | 51,253 |
| note | [approve](https://sepolia.basescan.org/tx/0xbcaf452f6223b9f6671468195fa1da8a4670863d732f42598d183a4f33320d93) | investor | 48239447 | 46,473 |
| note | [approve](https://sepolia.basescan.org/tx/0x88c5346bf469ea85c6d84d2503faa5ad5841c666b62b60e9bf1876ed718069d4) | buyer | 48239450 | 46,473 |
| note | [investor buys 1,000 notes](https://sepolia.basescan.org/tx/0x82d91aa09e7bb229251ae56fc73b64d33890aa3d3c3fc242e581360b2945e529) | investor | 48239453 | 83,155 |
| note | [settle the note](https://sepolia.basescan.org/tx/0x615311b8c6a3424dba29e511e8cb32c6dccab8f6e836630fdcd2241e68ddfc60) | investor | 48239539 | 51,796 |
| note | [issuer funds the coupon](https://sepolia.basescan.org/tx/0xf1c2c11355c10f72383745e8f9e890080df228c6bec9cad927f26609a616be0e) | buyer | 48239543 | 84,744 |
| note | [investor claims coupon](https://sepolia.basescan.org/tx/0x345c004c41ac63932a34e83923b518de711be1be8e1336a939f31eb512de9d19) | investor | 48239546 | 82,591 |
| agent_reveal | [reveal plan 2025-11-10](https://sepolia.basescan.org/tx/0x2f41a24bfac15ba4b7ecc41739b3d03113bca0a1d12a4daff928f26fe5bbbedc) | agent | 48239551 | 98,650 |
| agent_reveal | [reveal plan 2025-11-11](https://sepolia.basescan.org/tx/0x3d7d6fde5b0d86d87db3f22e555add0a27e231dc13d3dc4cb5c27bd745f96e18) | agent | 48239554 | 101,770 |
| agent_reveal | [reveal plan 2025-11-12](https://sepolia.basescan.org/tx/0xf1a3af696ac3f4fb1046717517f7d1990249143a12d303a1e05d9a6b8f1bd21b) | agent | 48239557 | 98,440 |
| agent_reveal | [reveal plan 2025-11-13](https://sepolia.basescan.org/tx/0xfcdd34018d4604fa3d4a0dda9a061876cf3fe657005d780a51c5a404a3b66fba) | agent | 48239560 | 99,600 |
| agent_reveal | [reveal plan 2025-11-14](https://sepolia.basescan.org/tx/0x0911d12eecd8ff09a9266f6f6958876c2390fccd22135177e4ab7a8c9f2e41f9) | agent | 48239563 | 100,520 |
| agent_reveal | [reveal plan 2025-11-15](https://sepolia.basescan.org/tx/0x1d10b7ea381ade822e6b84b4c1468520a816023dd6951e3fcb63192673c4ab73) | agent | 48239567 | 102,280 |
| agent_reveal | [reveal plan 2025-11-16](https://sepolia.basescan.org/tx/0x23e1619a3a6f848d6574c5bbe24a297cc1bf565e17395a36bca7319629217804) | agent | 48239569 | 101,950 |

## Attacks

| Attack | Expected | Observed |
|---|---|---|
| Registry B re-sells 50 MWh of hour 57 that the buyer already claimed | `SliceAlreadyClaimed` | `SliceAlreadyClaimed` (blocked) |
| Issuer certifies 1 MWh more than the metered production of that hour | `ExceedsProduction` | `ExceedsProduction` (blocked) |
| Someone impersonates issuer A with a different ML-DSA key | `BadIssuerSignature` | `BadIssuerSignature` (blocked) |
| Buyer tries to prove 77.48% (one basis point above the truth) | `ProverRefused` | `ProverRefused` (blocked) |
| Buyer resubmits the valid proof claiming 5 points more | `ProofRejected` | `ProofRejected` (blocked) |
| Buyer tries to prove residual ≤ 546.124 t (1 kg below the truth) | `ProverRefused` | `ProverRefused` (blocked) |
| Oracle re-posts hour 104 (133 g/kWh) 100 g/kWh cleaner | `AlreadyPosted` | `AlreadyPosted` (blocked) |
| Buyer proves residual ≤ 379.2 t on a fake intensity vector 30 % cleaner than the oracle's | `ProofRejected` | `ProofRejected` (blocked) |

## Files (SHA-256)

Byte-identical copies of `data/runs/20261017T141639Z/` (which stays git-ignored locally). The state file was written with every signing key scrubbed; a scan for the admin key and all derived keys finds none.

| File | SHA-256 |
|---|---|
| `independent-checks.txt` | `b5745d25225fbddd9c0f0ae1766803bd6818ce9bf1fcf1cae9f1f26d49358ce2` |
| `plans/2025-11-10.json` | `f92cf87d2580e37bd2f94b3cacb41db8cb06948b704fdf8aeb00329b55cf6950` |
| `plans/2025-11-11.json` | `0c1e09ca324cd23b27c388fd729699f3b8d1ec2e14c60ebc0b2222be2518a8e6` |
| `plans/2025-11-12.json` | `34aaf154153571425e6c37c2ef7d0e0ad367372d7c75757b0977ee8d956a0d2f` |
| `plans/2025-11-13.json` | `d5da72ca29612d89af3dc2e23236e7b04880d9cfabc816c06bb9ea738ace49f9` |
| `plans/2025-11-14.json` | `8695881a66629f0a864263842a229edf6c0d9dddc0f0a8380c0eeb1d5d4cb22a` |
| `plans/2025-11-15.json` | `4373248f1cc937eb1752b64307fcb565607c6ee27211ad565be39a3411e88b5a` |
| `plans/2025-11-16.json` | `20cbe2704b17e85b8a76da40976b7beeeada1bd821160f4220b3c11c208c4f62` |
| `proof/proof` | `992ae9a293b9a7594cd07215f15c69a99a811733ce4adbc715dcb5973441a23b` |
| `proof/public_inputs` | `5269cb3cc92e8ba1ea3b72937dce83aa43b6d5fa9e079e369bbbe1540257cd31` |
| `proof_emissions/proof` | `dfea1bed81ee1f84c54a934595f4ffbfeaec23339179393c58b97c51e05740fb` |
| `proof_emissions/public_inputs` | `2b7cca70ce05331c5ef30a4933f4c3b0bbc41c197a8e5237c63a34bffe2efdd3` |
| `proof_fake_intensity/proof` | `eb2bec9974fe6d8e3f5e8cf6522055c8b61a363e9dc8a12e00aebc30b3a0b26e` |
| `proof_fake_intensity/public_inputs` | `4629d6b2dd28663373e76cdb3d7f29d467dc86bc640e4bce369967a0039a946a` |
| `state.json` | `cfab1959140894dc1e39591116b6629b8c876e6f879b5881220010e132ec46de` |
| `verify.txt` | `58dbe2bf5985a8c8ef18200741373c05a47c1b0dfa06999f723d3ca157f4b603` |
