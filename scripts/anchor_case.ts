import * as anchor from "@coral-xyz/anchor";
import { PublicKey, SystemProgram } from "@solana/web3.js";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";

type AnchorPayload = {
  case_id: string;
  verdict_code: number;
  hashes: Record<
    | "case_id_hash"
    | "case_hash"
    | "pass_hash"
    | "capsule_hash"
    | "receipt_hash"
    | "review_hash"
    | "accountability_head_hash",
    string
  >;
};

function readJson<T>(path: string): T {
  return JSON.parse(readFileSync(path, "utf8")) as T;
}

function hex32(value: string): number[] {
  const normalized = value.startsWith("0x") ? value.slice(2) : value;
  if (!/^[0-9a-fA-F]{64}$/.test(normalized)) {
    throw new Error(`expected 32-byte hex string, got: ${value}`);
  }
  return Array.from(Buffer.from(normalized, "hex"));
}

function readKeypair(path: string): anchor.web3.Keypair {
  const raw = JSON.parse(readFileSync(path, "utf8")) as number[];
  return anchor.web3.Keypair.fromSecretKey(Uint8Array.from(raw));
}

async function main(): Promise<void> {
  const payloadPath = resolve(process.env.AEP_ANCHOR_PAYLOAD ?? "artifacts/anchor/aep-anchor-payload.json");
  const idlPath = resolve(process.env.AEP_ANCHOR_IDL ?? "target/idl/aep_proof_anchor.json");
  const walletPath = resolve(
    process.env.ANCHOR_WALLET ?? process.env.SOLANA_WALLET ?? `${process.env.HOME}/.config/solana/id.json`,
  );
  const rpcUrl = process.env.ANCHOR_PROVIDER_URL ?? process.env.SOLANA_RPC_URL ?? "https://api.devnet.solana.com";

  const payload = readJson<AnchorPayload>(payloadPath);
  const idl = readJson<anchor.Idl>(idlPath);
  const wallet = new anchor.Wallet(readKeypair(walletPath));
  const provider = new anchor.AnchorProvider(new anchor.web3.Connection(rpcUrl, "confirmed"), wallet, {
    commitment: "confirmed",
  });
  anchor.setProvider(provider);

  const program = new anchor.Program(idl, provider);
  const caseIdHash = Buffer.from(hex32(payload.hashes.case_id_hash));
  const [caseAnchor] = PublicKey.findProgramAddressSync(
    [Buffer.from("aep-case"), wallet.publicKey.toBuffer(), caseIdHash],
    program.programId,
  );

  const txSig = await program.methods
    .createCaseAnchor({
      caseIdHash: hex32(payload.hashes.case_id_hash),
      caseHash: hex32(payload.hashes.case_hash),
      passHash: hex32(payload.hashes.pass_hash),
      capsuleHash: hex32(payload.hashes.capsule_hash),
      receiptHash: hex32(payload.hashes.receipt_hash),
      reviewHash: hex32(payload.hashes.review_hash),
      accountabilityHeadHash: hex32(payload.hashes.accountability_head_hash),
      verdictCode: payload.verdict_code,
    })
    .accountsStrict({
      caseAnchor,
      authority: wallet.publicKey,
      systemProgram: SystemProgram.programId,
    })
    .rpc();

  const explorerUrl = `https://explorer.solana.com/tx/${txSig}?cluster=devnet`;
  const record = {
    ok: true,
    case_id: payload.case_id,
    program_id: program.programId.toBase58(),
    case_anchor: caseAnchor.toBase58(),
    authority: wallet.publicKey.toBase58(),
    signature: txSig,
    explorer_url: explorerUrl,
    rpc_url: rpcUrl,
    payload_path: payloadPath,
  };
  const outPath = resolve("artifacts/anchor/latest-devnet-anchor.json");
  mkdirSync(dirname(outPath), { recursive: true });
  writeFileSync(outPath, `${JSON.stringify(record, null, 2)}\n`);
  console.log(JSON.stringify(record, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
