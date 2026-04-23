use anchor_lang::prelude::*;

declare_id!("5LY2YsVpAhES2nq9TT7iQn4gGAy8vdb4nkE3XyQzMw4q");

#[program]
pub mod aep_proof_anchor {
    use super::*;

    pub fn create_case_anchor(
        ctx: Context<CreateCaseAnchor>,
        args: CreateCaseAnchorArgs,
    ) -> Result<()> {
        require!(
            args.verdict_code <= AepCaseAnchor::MAX_VERDICT_CODE,
            AepProofAnchorError::InvalidVerdictCode
        );

        let clock = Clock::get()?;
        let case_anchor = &mut ctx.accounts.case_anchor;
        case_anchor.schema_version = AepCaseAnchor::SCHEMA_VERSION;
        case_anchor.authority = ctx.accounts.authority.key();
        case_anchor.case_id_hash = args.case_id_hash;
        case_anchor.case_hash = args.case_hash;
        case_anchor.pass_hash = args.pass_hash;
        case_anchor.capsule_hash = args.capsule_hash;
        case_anchor.receipt_hash = args.receipt_hash;
        case_anchor.review_hash = args.review_hash;
        case_anchor.accountability_head_hash = args.accountability_head_hash;
        case_anchor.verdict_code = args.verdict_code;
        case_anchor.created_at = clock.unix_timestamp;
        case_anchor.bump = ctx.bumps.case_anchor;

        emit!(AepCaseAnchored {
            authority: case_anchor.authority,
            case_id_hash: case_anchor.case_id_hash,
            case_hash: case_anchor.case_hash,
            pass_hash: case_anchor.pass_hash,
            capsule_hash: case_anchor.capsule_hash,
            receipt_hash: case_anchor.receipt_hash,
            review_hash: case_anchor.review_hash,
            accountability_head_hash: case_anchor.accountability_head_hash,
            verdict_code: case_anchor.verdict_code,
            created_at: case_anchor.created_at,
        });

        Ok(())
    }
}

#[derive(Accounts)]
#[instruction(args: CreateCaseAnchorArgs)]
pub struct CreateCaseAnchor<'info> {
    #[account(
        init,
        payer = authority,
        space = 8 + AepCaseAnchor::LEN,
        seeds = [b"aep-case", authority.key().as_ref(), args.case_id_hash.as_ref()],
        bump
    )]
    pub case_anchor: Account<'info, AepCaseAnchor>,

    #[account(mut)]
    pub authority: Signer<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(AnchorSerialize, AnchorDeserialize, Clone, Debug, PartialEq, Eq)]
pub struct CreateCaseAnchorArgs {
    pub case_id_hash: [u8; 32],
    pub case_hash: [u8; 32],
    pub pass_hash: [u8; 32],
    pub capsule_hash: [u8; 32],
    pub receipt_hash: [u8; 32],
    pub review_hash: [u8; 32],
    pub accountability_head_hash: [u8; 32],
    pub verdict_code: u8,
}

#[account]
pub struct AepCaseAnchor {
    pub schema_version: u16,
    pub authority: Pubkey,
    pub case_id_hash: [u8; 32],
    pub case_hash: [u8; 32],
    pub pass_hash: [u8; 32],
    pub capsule_hash: [u8; 32],
    pub receipt_hash: [u8; 32],
    pub review_hash: [u8; 32],
    pub accountability_head_hash: [u8; 32],
    pub verdict_code: u8,
    pub created_at: i64,
    pub bump: u8,
}

impl AepCaseAnchor {
    pub const SCHEMA_VERSION: u16 = 1;
    pub const MAX_VERDICT_CODE: u8 = 5;
    pub const LEN: usize = 2 + 32 + (32 * 7) + 1 + 8 + 1;
}

#[event]
pub struct AepCaseAnchored {
    pub authority: Pubkey,
    pub case_id_hash: [u8; 32],
    pub case_hash: [u8; 32],
    pub pass_hash: [u8; 32],
    pub capsule_hash: [u8; 32],
    pub receipt_hash: [u8; 32],
    pub review_hash: [u8; 32],
    pub accountability_head_hash: [u8; 32],
    pub verdict_code: u8,
    pub created_at: i64,
}

#[error_code]
pub enum AepProofAnchorError {
    #[msg("Invalid AEP verdict code.")]
    InvalidVerdictCode,
}
