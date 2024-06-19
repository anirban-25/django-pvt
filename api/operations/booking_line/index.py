from api.common.constants import PALLETS, SKIDS


def handle_zero(line, client=None):
    # No property | "" | "0"
    length = float(line.get("l_005_dim_length", 0))
    width = float(line.get("l_006_dim_width", 0))
    height = float(line.get("l_007_dim_height", 0))
    weight = float(line.get("l_009_weight_per_each", 0))

    if length == 0 or width == 0 or height == 0 or weight == 0:
        zero_dims = []
        if not length:
            zero_dims.append("length")
        if not width:
            zero_dims.append("width")
        if not height:
            zero_dims.append("height")
        if not weight:
            zero_dims.append("weight")

        # Anchor Packaging Pty Ltd
        if client and client.dme_account_num == "49294ca3-2adb-4a6e-9c55-9b56c0361953":
            line["l_003_item"] += f" (ZERO Dims - {', '.join(zero_dims)})"
            line["l_004_dim_UOM"] = "m"
            line["l_008_weight_UOM"] = "kg"
            line["l_005_dim_length"] = line["l_005_dim_length"] or 0.25
            line["l_006_dim_width"] = line["l_006_dim_width"] or 0.25
            line["l_007_dim_height"] = line["l_007_dim_height"] or 0.25
            line["l_009_weight_per_each"] = line["l_009_weight_per_each"] or 1
        # Aberdeen Paper
        elif (
            client and client.dme_account_num == "4ac9d3ee-2558-4475-bdbb-9d9405279e81"
        ):
            line["l_003_item"] += f" (ZERO Dims - {', '.join(zero_dims)})"
            line["l_004_dim_UOM"] = line.get("l_004_dim_UOM", "m")
            line["l_008_weight_UOM"] = line.get("l_008_weight_UOM", "kg")
            line["l_005_dim_length"] = float(line.get("l_005_dim_length", 0)) or 0.11
            line["l_006_dim_width"] = float(line.get("l_006_dim_width", 0)) or 0.11
            line["l_007_dim_height"] = float(line.get("l_007_dim_height", 0)) or 0.11
            line["l_009_weight_per_each"] = (
                float(line.get("l_009_weight_per_each", 0)) or 1
            )
        # JasonL
        elif (
            client and client.dme_account_num == "1af6bcd2-6148-11eb-ae93-0242ac130002"
        ):
            if line["l_001_type_of_packaging"] in SKIDS:
                line["l_003_item"] += f" (ZERO Dims - {', '.join(zero_dims)})"
                line["l_004_dim_UOM"] = "m"
                line["l_008_weight_UOM"] = "kg"
                line["l_005_dim_length"] = line["l_005_dim_length"] or 1.2
                line["l_006_dim_width"] = line["l_006_dim_width"] or 1.2
                line["l_007_dim_height"] = line["l_007_dim_height"] or 1.2
                line["l_009_weight_per_each"] = line["l_009_weight_per_each"] or 100
            else:
                line["l_003_item"] += f" (ZERO Dims - {', '.join(zero_dims)})"
                line["l_004_dim_UOM"] = "m"
                line["l_008_weight_UOM"] = "kg"
                line["l_005_dim_length"] = line["l_005_dim_length"] or 0.1
                line["l_006_dim_width"] = line["l_006_dim_width"] or 0.1
                line["l_007_dim_height"] = line["l_007_dim_height"] or 0.1
                line["l_009_weight_per_each"] = line["l_009_weight_per_each"] or 1
        else:
            line["l_003_item"] += f" (ZERO Dims - {', '.join(zero_dims)})"
            line["l_004_dim_UOM"] = "m"
            line["l_008_weight_UOM"] = "kg"
            line["l_005_dim_length"] = line["l_005_dim_length"] or 0.5
            line["l_006_dim_width"] = line["l_006_dim_width"] or 0.5
            line["l_007_dim_height"] = line["l_007_dim_height"] or 0.5
            line["l_009_weight_per_each"] = line["l_009_weight_per_each"] or 1

    return line
