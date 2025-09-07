def american_to_decimal(american_odds):
    """
    Convert American odds to decimal odds
    
    Args:
        american_odds (int): American odds (e.g., +150, -200)
    
    Returns:
        float: Decimal odds
    """
    if american_odds > 0:
        # Positive odds: +X => 1 + X/100
        return 1 + american_odds / 100
    else:
        # Negative odds: -Y => 1 + 100/abs(Y)
        return 1 + 100 / abs(american_odds)

def decimal_to_american(decimal_odds):
    """
    Convert decimal odds to American odds
    
    Args:
        decimal_odds (float): Decimal odds
    
    Returns:
        int: American odds
    """
    if decimal_odds >= 2.0:
        # Positive American odds
        return int((decimal_odds - 1) * 100)
    else:
        # Negative American odds
        return int(-100 / (decimal_odds - 1))

def calculate_parlay_payout(stake_cents, decimal_odds):
    """
    Calculate parlay payout in cents
    
    Args:
        stake_cents (int): Stake amount in cents
        decimal_odds (float): Combined decimal odds
    
    Returns:
        int: Payout amount in cents (rounded)
    """
    payout = stake_cents * decimal_odds
    return round(payout)
